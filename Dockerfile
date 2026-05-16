FROM python:3.12-slim

# Build arguments / defaults (can be overridden at build time)
ARG SEG_CONTAINER_USER=seg
ARG SEG_CONTAINER_GROUP=seg
ARG SEG_CONTAINER_UID=1001
ARG SEG_CONTAINER_GID=1001
ARG SEG_PORT=8080
ARG SEG_APP_VERSION=0.1.0

ENV PATH="/usr/local/bin:$PATH"

# Install runtime deps (libmagic) and curl for healthcheck
# Distribution is upgraded to apply security updates and ensure latest bug fixes
# apt-get cleanup is done in the same layer to minimize image size
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get dist-upgrade -y \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libmagic1 \
        file \
    && apt-get purge -y --auto-remove \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root group/user (deterministic, minimal, hadolint-clean)
RUN groupadd \
      --gid ${SEG_CONTAINER_GID} \
      ${SEG_CONTAINER_GROUP} \
  || true \
  && useradd \
      --uid ${SEG_CONTAINER_UID} \
      --gid ${SEG_CONTAINER_GID} \
      --no-log-init \
      --create-home \
      --shell /sbin/nologin \
      ${SEG_CONTAINER_USER} \
  || true

WORKDIR /app

# Install Python runtime dependencies only
COPY requirements/runtime.txt ./requirements/runtime.txt
RUN python -m pip install --no-cache-dir -r requirements/runtime.txt

# Copy application code into the image root so the package `seg` is importable
# from the container working directory (i.e. /app/seg).
# Non-root ownership is ensured at copy time to avoid needing a separate chown layer.
COPY --chown=${SEG_CONTAINER_USER}:${SEG_CONTAINER_GROUP} src/ .

# Remove group/other write permissions from /app to enforce least-privilege and normalize modes after COPY
RUN chmod -R go-w /app

# Switch to non-root
USER ${SEG_CONTAINER_USER}

# Runtime environment defaults (can be overridden by docker-compose/env)
ENV SEG_PORT=${SEG_PORT}
ENV SEG_APP_VERSION=${SEG_APP_VERSION}

# Expose service port for Docker networking (optional; compose may override)
EXPOSE ${SEG_PORT}

# Start the FastAPI app with Uvicorn (shell form so env vars are expanded)
CMD ["sh", "-c", "uvicorn --factory seg.app:create_app --host 0.0.0.0 --port ${SEG_PORT} --proxy-headers --no-server-header"]

# Healthcheck hits internal health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"SEG_PORT\", \"8080\")}/health', timeout=2).read()" || exit 1
