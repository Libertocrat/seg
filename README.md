# Secure Execution Gateway (SEG)

Secure Execution Gateway (SEG) is a hardened internal microservice designed to replace unsafe operating system command execution patterns in **n8n** workflows.

SEG provides a strictly allowlisted, authenticated, and auditable HTTP API for controlled file-related operations, enabling production-grade automation without exposing the host or the n8n container to arbitrary command execution risks.

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

  - Share a mounted volume (`SEG_FS_ROOT`)
  - Communicate over an internal Docker network
- n8n interacts with SEG using the **HTTP Request** node

SEG is never exposed publicly and should only be reachable from trusted internal services.

---

## Features (v1)

- SHA-256 file hashing (`sha256_file`)
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
- All paths are resolved under `SEG_FS_ROOT`
- Operations are restricted to allowlisted subdirectories defined by `SEG_ALLOWED_SUBDIRS`
- Path traversal (`..`) is rejected
- Symbolic links are always rejected
- Windows-style paths and null bytes are rejected

---

### Resource Limits

Settings are configurable via `.env` file, these are the default values:

- Maximum file size: **100 MB**
- Request timeout: **5000 ms**
- Configurable rate limiting per client (default: 10 RPS)

---

## API Response Contract

All endpoints return responses wrapped in a consistent envelope:

```json
{
  "success": true,
  "data": { },
  "error": null,
  "request_id": "uuid"
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
  },
  "request_id": "uuid"
}
```

This contract is shared with other backends developed by [Libertocrat](https://github.com/Libertocrat/) to ensure uniform client behavior across services.

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
  "action": "sha256_file",
  "params": {
    "path": "uploads/file.bin"
  }
}
```

Example response:

```json
{
  "success": true,
  "data": {
    "sha256": "abc123...",
    "size_bytes": 20480
  },
  "error": null,
  "request_id": "7c9b0c44-..."
}
```

---

## Supported Actions (v1)

- `sha256_file`
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
- `SEG_FS_ROOT` (required)
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

## Observability

- **Logs**: Structured JSON logs to stdout
- **Metrics**: Prometheus-compatible metrics at `/metrics`
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

## License

MIT

## Author / Maintainer

[Libertocrat](https://github.com/Libertocrat)

---
