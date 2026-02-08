# **Software Requirements Specification (SRS)**

## Secure Execution Gateway (SEG) for n8n

**Version:** 1.0
**Status:** Approved
**Language:** Python
**Framework:** FastAPI + Pydantic
**Deployment:** Docker (rootless, Linux-only)

---

## 1. Introduction

### 1.1 Purpose

This document specifies the functional and non-functional requirements for the **Secure Execution Gateway (SEG)**.

SEG is a hardened internal microservice designed to replace unsafe OS command execution patterns in **n8n** workflows. Instead of allowing arbitrary shell execution inside the n8n container, SEG exposes a **strictly allowlisted**, **auditable**, and **authenticated** HTTP API for controlled file-related operations.

This SRS is intended for:

- Developers implementing SEG
- Security reviewers
- Infrastructure engineers integrating SEG with n8n

---

### 1.2 Scope

SEG provides:

- A small, well-defined set of **file operations** needed by production workflows
- Strong **filesystem sandboxing**
- **Defense-in-depth** against RCE, path traversal, and privilege escalation
- **Consistent API contracts** aligned with existing microservices coded my [Libertocrat](https://github.com/Libertocrat/)
- Observability via logs and Prometheus metrics

SEG explicitly **does not** aim to be a general-purpose execution engine.

---

### 1.3 Definitions

- **SEG**: Secure Execution Gateway
- **Sandbox Dir**: Shared filesystem mount accessible by n8n and SEG (configured via `SEG_SANDBOX_DIR`)
- **Allowlisted Subdirectories**: Explicit subfolders under the sandbox directory where operations are permitted
- **Action**: A named, predefined operation (e.g., `sha256_file`)
- **Envelope**: Standard API response structure used across shared services

#### Authors / Maintainers

- Libertocrat - <libertocrat@proton.me> : Project lead, design and implementation.

---

## 2. System Overview

### 2.1 High-Level Architecture

- n8n runs in a Docker container
- SEG runs in a **separate rootless Docker container**
- Both containers:
  - Are on the same internal Docker network
  - Share a volume mounted on a sandbox directory (`SEG_SANDBOX_DIR`)
- n8n calls SEG via HTTP using the **HTTP Request node**
- SEG never executes arbitrary commands and never exposes a shell

---

### 2.2 Design Goals

- Eliminate arbitrary command execution in n8n and other microservices
- Enforce least privilege and explicit intent
- Maintain consistent API typing across services
- Be simple to deploy and reason about
- Be extensible without breaking contracts

---

## 3. Assumptions and Constraints

### 3.1 Assumptions

- Single-tenant deployment
- Linux-only environment
- Internal network access only (not publicly exposed)
- n8n already performs input sanitization at workflow level
- Shared docker volume between consumer microservices, mounted in SEG to perform file operations

### 3.2 Constraints

- SEG must run rootless
- All filesystem operations must be sandboxed
- Only synchronous API is supported in v1
- Maximum file size: **100 MB**
- Request timeout: **5000 ms**

---

## 4. Security Model

### 4.1 Authentication

- All `/v1/*` endpoints require authentication
- Header:

  ```http
  Authorization: Bearer <SEG_API_TOKEN>
  ```

- Token is configured via environment variables
- Missing or invalid token -> `401 Unauthorized`

---

### 4.2 Filesystem Sandbox

SEG enforces a strict sandbox:

- All paths must be **relative**
- Paths are resolved against `SEG_SANDBOX_DIR`
- Resolved path must:

  - Stay within `SEG_SANDBOX_DIR`
  - Belong to one of the `SEG_ALLOWED_SUBDIRS`
- Path traversal (`..`) is rejected
- Symlinks are **always rejected**
- Windows-style paths are rejected
- Null bytes are rejected

Notes:

- `SEG_ALLOWED_SUBDIRS` examples: `/quarantine`, `/uploads`, `/outputs` (CSV: `quarantine,uploads,outputs`).
-- If `SEG_ALLOWED_SUBDIRS` is empty, SEG will allow access to any path under the configured `SEG_SANDBOX_DIR` (permissive fallback; use with caution).

---

### 4.3 Command Execution Policy

- SEG does **not** accept command strings
- SEG does **not** expose a shell
- Each operation is implemented as a **dedicated action**
- All parameters are validated via Pydantic models

---

### 4.4 Resource Protection

- Maximum file size enforced (`SEG_MAX_BYTES = 104857600`)
- Per-request timeout enforced (`SEG_TIMEOUT_MS = 5000`)
- Rate limiting enabled (`SEG_RATE_LIMIT_RPS`)
- All operations are bounded and deterministic

---

## 5. API Design

### 5.1 Response Contract (Global)

All API responses MUST follow this envelope. Request correlation is
performed via the `X-Request-Id` response header (UUID). The JSON body
envelope does not include `request_id` to avoid duplication; clients must
read the header for the UUID used for logs/metrics correlation.

```python
class Response():
  success: bool
  data: Optional[DataItem] = None
  error: Optional[ErrorInfo] = None
```

```python
class ErrorInfo():
  message: str
  code: Optional[str] = None
  details: Optional[Dict[str, Any]] = None
```

#### Rules

- `success == true` -> `data` MUST be present, `error` MUST be null
- `success == false` -> `error` MUST be present, `data` MUST be null
- `X-Request-Id` MUST always be present in response headers at runtime (and present in logs and metrics). The server will accept a client-supplied `X-Request-Id` header if it is a valid UUID; otherwise the server generates a new UUID and returns it in the response header.

Note: `/metrics` is an explicit exception to the JSON envelope requirement. It returns the Prometheus exposition format and is intentionally not wrapped in the JSON response envelope so that Prometheus scrapers can ingest it.

This contract is **shared with the other microservices** to ensure consistency.

---

### 5.2 Request Identification

- A UUID `request_id` (UUID) is generated for every request if the client does not provide a valid `X-Request-Id` header. The value is always returned to the client in the `X-Request-Id` response header and is present in logs and metrics for correlation.
- Included in:

  - Header
  - Logs
  - Metrics labels (where applicable)

---

### 5.3 Error Codes (Stable)

HTTP status mapping (initial, to be refined per-endpoint):

- `INVALID_REQUEST` -> 400
- `UNAUTHORIZED` -> 401
- `PATH_NOT_ALLOWED` -> 403
- `FILE_NOT_FOUND` -> 404
- `FILE_TOO_LARGE` -> 413
- `CONFLICT` -> 409
- `RATE_LIMITED` -> 429
- `INTERNAL_ERROR` -> 500

---

## 6. API Endpoints

### 6.1 Health Check

**GET `/health`**

Response:

```json
{
  "status": "ok"
}
```

---

### 6.2 Metrics

**GET `/metrics`**

- Prometheus exposition format
- Used for latency, error, and throughput monitoring

---

### 6.3 Execute Action

**POST `/v1/execute`**

#### Request

```json
{
  "action": "sha256_file",
  "params": {
    "path": "uploads/file.bin"
  }
}
```

#### Response (success)

```json
{
  "success": true,
  "data": {
    "sha256": "abc...",
    "size_bytes": 12345
  },
  "request_id": "uuid"
}
```

---

## 7. Functional Requirements (Actions)

### 7.1 `sha256_file`

- Computes SHA-256 using streaming I/O
- Params:

  - `path` (relative)
- Output:

  - `sha256`
  - `size_bytes`

---

### 7.2 `stat_file`

- Params:

  - `path`
- Output:

  - `exists`
  - `is_file`
  - `size_bytes`
  - `mtime_epoch`

---

### 7.3 `delete_file`

- Params:

  - `path`
  - `require_exists` (default false)
- Output:

  - `deleted` (bool)

---

### 7.4 `move_file` (includes rename)

- Params:

  - `src_path`
  - `dst_path`
  - `overwrite` (default false)
- Rules:

  - Both paths must be inside allowlisted subdirs
  - If destination already exists and `overwrite` is `false`, return `CONFLICT` (409) and do not overwrite.
- Output:

  - `moved`
  - `src`
  - `dst`

---

### 7.5 `mime_detect`

- Uses `libmagic`
- Params:

  - `path`
- Output:

  - `mime`

Implementation note: the runtime must include the system `libmagic` library and a stable Python binding (for example `python-magic`). Implementations MUST detect MIME type from file content (not filename extension) using libmagic or an equivalent system-level library.

---

### 7.6 `verify_file` (Composite)

- Params:

  - `path`
  - `expected_sha256` (optional)
  - `expected_mime_prefixes` (optional)
- Output:

  - `sha256`
  - `mime`
  - `size_bytes`
  - `hash_matches`
  - `mime_allowed`

> Antivirus and sandbox scanning are **explicitly out of scope for v1**.

---

## 8. Observability Requirements

### 8.1 Logging

- JSON logs to stdout
- Required fields:

  - timestamp
  - level
  - request_id
  - action
  - duration_ms
  - result (success/error + code)
  - caller (optional): include when provided by the client (for example, an n8n workflow id). By default include host:port information.

---

### 8.2 Metrics (Prometheus)

- Request count by action and status
- Request latency histogram
- Error count by code
- Rate-limit rejections

Implementation note: start with the Prometheus client library defaults for histogram buckets; buckets may be tuned later.

---

## 9. Configuration

### 9.1 Environment Variables

- `SEG_API_TOKEN` (required)
- `SEG_SANDBOX_DIR` (required)
- `SEG_ALLOWED_SUBDIRS` (CSV, required)
- `SEG_MAX_BYTES=104857600` (100 MB)
- `SEG_TIMEOUT_MS=5000` (ms)
- `SEG_RATE_LIMIT_RPS=10` (defaults to 10 RPS when not defined)
- `SEG_LOG_LEVEL=INFO`

Notes:

- `SEG_API_TOKEN` for v1: single static token provided via environment (or `.env`) for MVP. Future versions may support token lists or JWTs with secrets stored in HashiCorp Vault.

---

## 10. Deployment Requirements

- Dockerfile (rootless)
- Standalone `docker-compose.yml`
- No public ports by default
- Healthcheck configured
- Minimal base image

---

## 11. Non-Goals (Explicit)

- Arbitrary shell execution
- Async job orchestration (v1)
- Antivirus / malware scanning (v1)
- Multi-tenant auth
- Media conversion

---

## 12. Acceptance Criteria

- All endpoints enforce auth
- All responses conform to envelope contract
- Path traversal and symlink escapes are rejected
- Max file size and timeout are enforced
- Metrics and logs are emitted correctly
- OpenAPI documentation is generated automatically

Operational decisions and clarifications:

- `request_id`: the server will accept a client-supplied `request_id` if it is a valid UUID; otherwise the server generates a UUID. `request_id` MUST always be present in responses, logs and metrics.
- Responses for files that exceed `SEG_MAX_BYTES` MUST use `FILE_TOO_LARGE` and HTTP 413.
- Symlink rejections and other sandbox violations SHOULD initially return `PATH_NOT_ALLOWED` (403).
- Testing: use `pytest` for unit and integration tests. Integration tests should exercise sandboxing using temporary directories or tmpfs; end-to-end scenarios can use `docker-compose`.
- OpenAPI: `/docs` will not be published in production by default. A generated Swagger/OpenAPI JSON file will be checked into the repository for external documentation.

---

## 13. Future Extensions (Not in Scope)

- Async jobs API
- External sandbox scanners (e.g., Strelka)
- Media conversion services
- Multi-tenant support

---
