# Secure Execution Gateway (SEG)

Secure Execution Gateway (SEG) is a hardened internal microservice designed to replace unsafe operating system command execution patterns in **n8n** workflows.

SEG provides a strictly allowlisted, authenticated, and auditable HTTP API for controlled file-related operations, enabling production-grade automation without exposing the host or the n8n container to arbitrary command execution risks.

## Contents

- [Quickstart](#quickstart)
- [Motivation](#motivation)
- [Design Principles](#design-principles)
- [High-Level Architecture](#high-level-architecture)
- [Features (v1)](#features-v1)
- [Security Model](#security-model)
- [Development & CI](#development--ci)
  - Note: CI checks include both `src/` and `tests/` (formatting, linting and
    type-checking). Run `make ci` locally to reproduce the full pipeline.
- [Troubleshooting](#troubleshooting)

---

## Quickstart

Prerequisites:

- Docker (engine) and Docker Compose v2 (or the `docker compose` command) installed
- A user with Docker privileges (or use `sudo` when invoking Docker commands)

Steps to run locally:

1. Copy the environment example and edit values:

```bash
cp .env.example .env
# Edit .env: set SEG_API_TOKEN, NON_ROOT_GID, COMPOSE_PROJECT_NAME, etc.
```

2. Make the shared volume initializer script executable and verify it:

```bash
chmod +x scripts/init-shared-volume.sh
./scripts/init-shared-volume.sh --env-file .env --dry-run
# Review the printed actions (no changes made).
```

3. Prepare the named Docker shared volume (apply changes):

```bash
./scripts/init-shared-volume.sh --env-file .env
# This creates the volume (if missing) and sets group/setgid permissions.
```

4. Start the stack:

```bash
docker compose up -d --build
# Check services: docker compose ps
```

5. Verify the service is healthy:

```bash
# Real-time logs
docker compose logs -f

# Health endpoint from shared network temporal container
docker run --rm --network $SHARED_DOCKER_NETWORK curlimages/curl -sS -f http://$COMPOSE_PROJECT_NAME-seg:$SEG_PORT/health && echo OK
```

Notes:

- The initializer requires `SHARED_VOLUME_NAME`, `NON_ROOT_GID`, and `SEG_ALLOWED_SUBDIRS` to be set in `.env` (see [scripts/specs/init-shared-volume.spec.md](scripts/specs/init-shared-volume.spec.md)).
- Run the init script as a user with Docker access; it performs operations inside a temporary container and does not mutate host paths directly.
- If you want to inspect what will change without applying it, use `--dry-run`.

---

## Motivation

Recent versions of n8n (v2.0 or later) disable high-risk execution nodes by default due to security concerns around remote code execution (RCE) found in late 2025 and January 2026, which are listed below.

While this improves safety, it also removes a common mechanism used for file hashing, cleanup, and validation inside workflows.

SEG addresses this gap by offering:

- Explicitly defined operations instead of free-form commands
- Strong filesystem sandboxing
- Rootless container execution
- Consistent API contracts aligned with backend services
- Observability through structured logs and metrics

SEG is designed for **self-hosted, Docker-based n8n deployments** where security, auditability, and operational clarity are required.

### Critical n8n Vulnerabilities (Dec 2025 - Jan 2026)

#### **CVE-2025-68613 - Remote Code Execution (Authenticated)**

- **Severity:** Critical (CVSS ~9.9)
- **Description:** A flaw in the workflow expression evaluation system allows an *authenticated attacker* to inject expressions that execute arbitrary code in the n8n process context
- **Affected Versions:** ~0.211.0 -> prior to 1.120.4, 1.121.1, 1.122.0 (fixed in those releases)
- **Impact:** Arbitrary code execution; complete instance compromise under certain authenticated scenarios
- **More Info:**

  - 🔗 [https://nvd.nist.gov/vuln/detail/CVE-2025-68613](https://nvd.nist.gov/vuln/detail/CVE-2025-68613)

#### **CVE-2026-21858 - "Ni8mare", Unauthenticated RCE**

- **Severity:** Critical / Maximum Severity (CVSS 10.0)
- **Nickname:** *Ni8mare*
- **Description:** Improper handling of webhook/form requests and content-type parsing enables *unauthenticated attackers* to access files, forge sessions, and **execute code remotely** on vulnerable self-hosted n8n instances
- **Affected Versions:** ~1.65.0 -> prior to 1.121.0 (fixed in 1.121.0)
- **Impact:** Full instance takeover without authentication if exposed workflows/webhook entry points exist
- **More Info:**

  - 🔗 [https://nvd.nist.gov/vuln/detail/CVE-2026-21858](https://nvd.nist.gov/vuln/detail/CVE-2026-21858)

#### **CVE-2026-21877 - Authenticated Remote Code Execution**

- **Severity:** Critical (CVSS ~9.9)
- **Description:** An issue where authenticated users can upload dangerous file types or abuse processing logic to execute arbitrary code via n8n.
- **Affected Versions:** ~<= 1.121.2 (fixed in 1.121.3)
- **Impact:** Authenticated RCE-enables full compromise of the n8n instance.
- **More Info:**

  - 🔗 [https://nvd.nist.gov/vuln/detail/CVE-2026-21877](https://nvd.nist.gov/vuln/detail/CVE-2026-21877) *(via Wiz/NVD summary)*

> SEG is not a patch for these vulnerabilities, but an architectural response to remove entire classes of unsafe execution patterns from automation workflows.

---

## Security & Responsible Disclosure

SEG is designed and developed with a security-first mindset.

If you discover a security vulnerability or have concerns related to authentication, sandboxing, or potential misuse scenarios, please **do not open a public issue**.

Instead, follow the responsible disclosure process described in [`SECURITY.md`](SECURITY.md).

For sensitive reports, encrypted communication is supported via the maintainer’s public PGP key, which is available in the file [SECURITY_PGP_KEY.asc](SECURITY_PGP_KEY.asc) at the root of this repository.

---

## Design Principles

- **No arbitrary command execution**
  SEG never accepts shell commands or command strings.

- **Allowlisted actions only**
  Each operation is explicitly defined and validated.

- **Defense in depth**
  Filesystem sandboxing, authentication, rate limiting, and resource limits are enforced at multiple layers.

- **Consistency by contract**
  API responses follow the same typed envelope used across shared microservices for consistency.

- **Operational simplicity**
  Sync API, minimal dependencies, Docker-first deployment.

---

## High-Level Architecture

- n8n runs in its own Docker container
- SEG runs in a separate, rootless Docker container
- Both containers:

  - Share a mounted sandbox directory (`SEG_SANDBOX_DIR`)
  - Communicate over an internal Docker network
- n8n interacts with SEG using the **HTTP Request** node

SEG is never exposed publicly and should only be reachable from trusted internal services.

---

## Features (v1)

- File hashing (`checksum_file`)
- File metadata inspection (`stat_file`)
- Safe file deletion (`delete_file`)
- File move / rename within sandbox (`move_file`)
- MIME type detection using libmagic (`mime_detect`)
- Composite verification (`verify_file`)

  - Hash computation
  - MIME policy validation
- Strict filesystem sandbox
- Bearer token authentication
- Rate limiting and timeouts
- Structured JSON logs
- Prometheus-compatible metrics
- Automatic OpenAPI / Swagger documentation

---

## Security Model

The security model of SEG is intentionally simple, explicit, and restrictive to minimize blast radius and audit complexity.

### Authentication

All API endpoints require a bearer token:

```http
Authorization: Bearer <SEG_API_TOKEN>
```

The token is provided via environment variables and injected at runtime. In future versions, multi-client/multi-user JWT authentication will be implemented.

---

### Filesystem Sandbox

SEG enforces strict path rules:

- Only **relative paths** are accepted
- All paths are resolved under `SEG_SANDBOX_DIR`
- Operations are restricted to allowlisted subdirectories defined by `SEG_ALLOWED_SUBDIRS`
- Path traversal (`..`) is rejected
- Symbolic links are always rejected
- Windows-style paths and null bytes are rejected

---

### Shared Volume Permission Model (setgid-based)

SEG is designed to safely share a filesystem volume with other internal services (such as n8n) **without requiring those services to be modified or hardened**.

This is achieved using a **POSIX group-based permission model** combined with the `setgid` directory bit.

#### Design Overview

- SEG runs as a **non-root user** (`UID=1001`, `GID=1001`)
- Other services (e.g. n8n) may run as `root` (default behavior)
- A shared filesystem volume is mounted into both containers
- The shared directory on the host is configured with:
  - Group ownership set to `GID=1001`
  - `setgid` enabled on the directory

#### Why setgid is critical

When the `setgid` bit is set on a directory:

- All files and subdirectories created inside it **inherit the directory’s group ID**
- The inherited group is used **regardless of the UID of the creating process**

This ensures that:

- Files created by `root`-based services (e.g. n8n) are automatically assigned to the shared group
- SEG (running as a non-root user) can safely read and write those files via group permissions
- No UID sharing, ACLs, or insecure permission workarounds are required

#### Required host-side setup

The shared volume **must be prepared on the host before starting the containers**.

Example:

```bash
mkdir -p /data/seg-shared
chown -R root:1001 /data/seg-shared
chmod -R 2775 /data/seg-shared
```

The leading `2` in `2775` enables `setgid`.

Expected permissions:

```text
drwxrwsr-x  root  seg  /data/seg-shared
```

#### Security properties

- SEG remains **rootless** at all times
- No container modifies users, groups, or permissions of other containers
- No reliance on `chmod 777`, ACLs, or privileged containers
- Volume access is governed strictly by:

  - POSIX group permissions
  - `setgid` inheritance
- This model scales cleanly to additional internal services that need filesystem access

This permission model is intentionally simple, auditable, and aligned with production-grade Docker and Kubernetes best practices.

---

### Resource Limits

Settings are configurable via `.env` file, these are the default values:

- Maximum file size: **100 MB**
- Request timeout: **5000 ms**
- Configurable rate limiting per client (default: 10 RPS)

---

## API Response Contract

All endpoints return responses wrapped in a consistent envelope in the JSON body:

```json
{
  "success": true,
  "data": { },
  "error": null
}
```

On error:

```json
{
  "success": false,
  "data": null,
  "error": {
    "message": "Resolved path is outside allowed sandbox",
    "code": "PATH_NOT_ALLOWED",
    "details": { }
  }
}
```

Responses also include a correlation header `X-Request-Id` (UUID). The header is propagated if the client supplies a valid UUID in the incoming `X-Request-Id` header; otherwise the server generates a new UUID. Clients should read `X-Request-Id` from headers for request correlation. Example JSON envelopes (note `request_id` is carried in the header, not the body)

This contract is shared with other backends developed by [Libertocrat](https://github.com/Libertocrat/) to ensure uniform client behavior across services. Always read the `X-Request-Id` response header for the UUID associated with the request.

---

## API Endpoints

### Health Check

**GET `/health`**

Returns service readiness status.

---

### Metrics

**GET `/metrics`**

Prometheus exposition endpoint for monitoring latency, error rates, and throughput.

---

### Execute Action

**POST `/v1/execute`**

Example request:

```json
{
  "action": "checksum_file",
  "params": {
    "path": "uploads/file.bin",
    "algorithm": "sha256"
  }
}
```

Example response:

```json
{
  "success": true,
  "data": {
    "algorithm": "sha256",
    "checksum": "abc123...",
    "size_bytes": 20480
  },
  "error": null
}
```

---

## Supported Actions (v1)

- `checksum_file`
- `stat_file`
- `delete_file`
- `move_file` (used for rename as well)
- `mime_detect`
- `verify_file`

Each action has a strict request schema validated using Pydantic models.

---

## Configuration

SEG is configured entirely via environment variables:

- `SEG_API_TOKEN` (required)
- `SEG_SANDBOX_DIR` (required)
- `SEG_ALLOWED_SUBDIRS` (CSV, required)
- `SEG_MAX_BYTES` (default: 104857600)
- `SEG_TIMEOUT_MS` (default: 5000)
- `SEG_RATE_LIMIT_RPS`
- `SEG_LOG_LEVEL` (default: INFO)

An `.env.example` file is recommended and is included in the repository to document required/runtime defaults.

---

## Deployment

SEG is designed to run as a rootless Docker container.

A standalone `docker-compose.yml` is included for local testing and integration with n8n or other microservices.
No public ports should be exposed in production environments.

---

## Development & CI

If you are a developer working on SEG, the repository provides a small set of guides to get started and to reproduce CI checks locally. Start here:

- Development quickstart and contribution guidelines: [CONTRIBUTING.md](CONTRIBUTING.md)
- CI pipeline, pre-commit policy and tooling requirements: [docs/CI.md](docs/CI.md)
- Testing philosophy and fixtures: [docs/TESTING.md](docs/TESTING.md)

These documents describe how to reproduce CI locally, the required system dependencies (Linux-based), and the `pre-commit` hooks used by the project.

---

## Observability

- **Logs**: Structured JSON logs to stdout
- **Metrics**: Prometheus-compatible metrics at `/metrics`
  - Note: `/metrics` is an exception to the JSON envelope contract. It exposes Prometheus exposition format and is intentionally not wrapped in the service's JSON response envelope so Prometheus scrapers can ingest it directly.
- **Tracing**: Request-level correlation via `request_id`

---

## Non-Goals (v1)

- Arbitrary shell execution
- Asynchronous job orchestration
- Antivirus or malware scanning
- Media conversion
- Multi-tenant authorization

These capabilities are intentionally excluded to keep the service focused, secure, and easy to reason about.

---

## Future Extensions

- Async job API for long-running tasks
- Integration with external sandbox scanners (e.g. Strelka)
- Media processing pipelines
- Multi-tenant support
- JWT authentication

---

## Troubleshooting

### Actions not registered at startup

If you add new actions under `src/seg/actions/` and they do not appear in the service registry at startup, ensure the action subdirectory is a Python package by adding an `__init__.py` file. Also export or import the action modules from that package's `__init__.py` (for example `from . import checksum`) so that importing the package triggers the registration side-effects.

Quick checks and fixes:

- Start the service with the project source on `PYTHONPATH` (example):

  ```bash
  # using the application factory
  PYTHONPATH=./src uvicorn --factory seg.app:create_app --host 0.0.0.0 --port 8080 --reload --reload-dir src --log-level info
  ```

  - Or install the package in editable mode and run normally:

  ```bash
  pip install -e .
  uvicorn --factory seg.app:create_app
  ```

- Verify registered actions quickly:

  ```bash
  PYTHONPATH=./src python -c "from seg.actions import discover_and_register; from seg.actions.registry import list_actions; discover_and_register(); print(list_actions())"
  ```

- Note: the runtime discovery imports `seg.actions` subpackages to execute registration side-effects. If a new action module is not imported (for example because the package `__init__.py` does not import it), that action will not be registered.

### Mypy execution throws an exception

- **Symptom**: After refactoring imports, `__init__.py` files, or the package layout, `mypy` (or the pre-commit `mypy` hook) may fail with an internal exception (for example `KeyError: 'is_bound'`) or report duplicate-module mapping errors.
- **Cause**: A stale `.mypy_cache` directory can contain serialized type information that is no longer compatible with the updated module graph.
- **Fix**: Remove the cache and re-run the checks:

```bash
rm -rf .mypy_cache
make ci   # or: pre-commit run --all-files
```

- **Note**: Clearing the mypy cache is a safe, local operation and does not affect runtime behavior. This is a known issue when making large structural changes; developers are encouraged to clear the cache after major refactors. Consider disabling incremental mode in CI if this occurs frequently.

## License

MIT

## Author / Maintainer

[Libertocrat](https://github.com/Libertocrat)

---
