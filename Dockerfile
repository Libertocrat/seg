FROM python:3.12-slim

# Build arguments / defaults (can be overridden at build time)
ARG NON_ROOT_USER=seg
ARG NON_ROOT_GROUP=seg
ARG NON_ROOT_UID=1001
ARG NON_ROOT_GID=1001
ARG SEG_PORT=8080

ENV PATH="/usr/local/bin:$PATH"

# Install runtime deps (libmagic) and curl for healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root group/user (deterministic, minimal, hadolint-clean)
RUN groupadd \
      --gid ${NON_ROOT_GID} \
      ${NON_ROOT_GROUP} \
  || true \
  && useradd \
      --uid ${NON_ROOT_UID} \
      --gid ${NON_ROOT_GID} \
      --no-log-init \
      --create-home \
      --shell /sbin/nologin \
      ${NON_ROOT_USER} \
  || true

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into the image root so the package `seg` is importable
# from the container working directory (i.e. /app/seg).
COPY src/ .

# Ensure correct ownership
RUN chown -R ${NON_ROOT_USER}:${NON_ROOT_GROUP} /app

# Switch to non-root
USER ${NON_ROOT_USER}

# Runtime environment defaults (can be overridden by docker-compose/env)
ENV SEG_PORT=${SEG_PORT}

# Expose service port for Docker networking (optional; compose may override)
EXPOSE ${SEG_PORT}

# Start the FastAPI app with Uvicorn (shell form so env vars are expanded)
CMD ["sh", "-c", "uvicorn seg.app:app --host 0.0.0.0 --port ${SEG_PORT} --proxy-headers"]

# Healthcheck hits internal health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:${SEG_PORT}/health || exit 1
