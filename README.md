<h1 align="center">Secure Execution Gateway</h1>

<p align="center">
  <img src="docs/assets/seg-logo-600x400.png" width="400" alt="SEG Logo">
</p>

<p align="center">
  <em>
    A security-focused execution gateway for automation platforms that replaces arbitrary command execution with DSL-defined, allowlisted operations.
  </em>
  <br>
  <em>
    Designed for secure automation, workflow engines, and internal platforms.
  </em>
</p>

<p align="center">
  <a href="https://github.com/Libertocrat/seg/releases">
    <img src="https://img.shields.io/github/v/release/Libertocrat/seg" alt="Release">
  </a>
  <a href="https://github.com/Libertocrat/seg/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/Libertocrat/seg" alt="License">
  </a>
  <a href="https://github.com/Libertocrat/seg/actions/workflows/ci.yml">
    <img src="https://github.com/Libertocrat/seg/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/Libertocrat/seg/actions/workflows/security.yml">
    <img src="https://github.com/Libertocrat/seg/actions/workflows/security.yml/badge.svg" alt="Security">
  </a>
  <a href="https://github.com/Libertocrat/seg/actions/workflows/release.yml">
    <img src="https://github.com/Libertocrat/seg/actions/workflows/release.yml/badge.svg" alt="Release Pipeline">
  </a>
  <a href="https://github.com/Libertocrat/seg/pkgs/container/seg">
    <img src="https://img.shields.io/badge/container-ghcr.io-blue?logo=docker" alt="Docker">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.12-blue?logo=python" alt="Python">
  </a>
  <a href="https://libertocrat.github.io/seg/api-docs/">
    <img src="https://img.shields.io/badge/OpenAPI-3.1-green" alt="OpenAPI">
  </a>
</p>

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. Motivation](#2-motivation)
- [3. Key Features](#3-key-features)
- [4. Architecture Overview](#4-architecture-overview)
- [5. Security Model](#5-security-model)
- [6. Quick Start](#6-quick-start)
- [7. Configuration](#7-configuration)
- [8. API Overview](#8-api-overview)
- [9. Observability](#9-observability)
- [10. Project Structure](#10-project-structure)
- [11. Testing Strategy](#11-testing-strategy)
- [12. CI / DevSecOps](#12-ci--devsecops)
- [13. Documentation](#13-documentation)
- [14. Development](#14-development)
- [15. Contributing](#15-contributing)
- [16. Security Reporting](#16-security-reporting)
- [17. License](#17-license)

## 1. Overview

Secure Execution Gateway (SEG) is a security-focused FastAPI microservice that exposes a small execution surface for DSL-defined actions together with SEG-managed file lifecycle API endpoints.

SEG acts as an internal execution gateway for automation and platform workflows that need controlled command execution and managed file exchange without exposing arbitrary shell access.

At startup, SEG loads YAML action definitions, validates them, compiles them into immutable runtime specs, and exposes them through authenticated discovery and execution endpoints at `/v1/actions`. File ingestion, retrieval, listing, download, and deletion are handled through the `/v1/files` API.

In practice, an action is a predefined command template compiled from YAML, not free-form shell submitted by the client. Callers only provide values for the parameters declared by that action.

> [!IMPORTANT]
> SEG was originally created as a secure alternative to unsafe command execution mechanisms commonly used in workflow automation platforms.
>
> Several critical Remote Code Execution vulnerabilities discovered in n8n between late 2025 and early 2026 (for example [CVE-2025-68613](https://nvd.nist.gov/vuln/detail/CVE-2025-68613), [CVE-2026-21858](https://nvd.nist.gov/vuln/detail/CVE-2026-21858), and [CVE-2026-21877](https://nvd.nist.gov/vuln/detail/CVE-2026-21877)) highlighted the risks of exposing arbitrary command execution inside automation systems.
>
> SEG addresses this class of problems by replacing free-form command execution with strictly validated DSL action specs and runtime policy checks executed inside a sandboxed environment.

### Execution Boundary Model

```mermaid
flowchart TD

subgraph Risky Automation Patterns
A[Arbitrary Command Execution]
B[Dynamic Expressions]
C[Unrestricted Scripts]
D[Privileged Workflow Automation]
end

subgraph SEG Execution Gateway
E[DSL-defined Actions]
F[Runtime Policy Enforcement]
G[Managed File API]
H[Observability and Auditability]
end

subgraph Controlled Operations
I[Deterministic Command Rendering]
J[Safe Automation Workflows]
end

A --> E
B --> E
C --> E
D --> E

E --> F
F --> G
G --> H
H --> I
I --> J
```

### Use Cases

Possible use cases include:

- Secure execution layer for automation platforms such as n8n
- Controlled filesystem operations in microservice architectures
- Secure file-processing gateway inside internal platforms
- Replacement for unsafe command execution patterns in backend services
- Hardened execution boundary for workflow engines and task runners

## 2. Motivation

The rapid adoption of low-code automation platforms, agentic AI systems, and workflow orchestration tools has dramatically increased the number of systems capable of executing complex automated tasks with access to sensitive data and infrastructure.

Many of these platforms prioritize **speed to market and ease of use** over defensive system design. As a result, execution primitives such as command execution, dynamic expressions, or unrestricted scripting frequently become high-risk attack surfaces.

When combined with:

- viral adoption of automation platforms
- widespread self-hosted deployments
- privileged access to internal systems and data
- limited security expertise among many users

these characteristics create a **high-risk environment for Remote Code Execution (RCE), privilege escalation, and data compromise**.

Secure Execution Gateway (SEG) was designed as an **architectural response** to this class of problems.

Instead of exposing arbitrary command execution, SEG introduces a hardened execution boundary where:

- operations are **explicitly allowlisted**
- filesystem access is **sandboxed and constrained**
- execution occurs inside a **rootless container environment**
- APIs enforce **typed request contracts**
- observability enables **traceable and auditable operations**

This model replaces unsafe execution patterns with **controlled, deterministic operations** suitable for automation systems that must balance flexibility with security.

### Example vulnerabilities illustrating the risk

Several critical vulnerabilities discovered in workflow automation platforms between late 2025 and early 2026 illustrate the inherent risk of exposing arbitrary execution capabilities.

| CVE | Type | Description |
| ---- | ---- | ---- |
| [CVE-2025-68613](https://nvd.nist.gov/vuln/detail/CVE-2025-68613) | Authenticated RCE | Expression evaluation flaw allowing code execution inside n8n workflows |
| [CVE-2026-21858](https://nvd.nist.gov/vuln/detail/CVE-2026-21858) | Unauthenticated RCE | "Ni8mare" vulnerability enabling remote takeover via webhook processing |
| [CVE-2026-21877](https://nvd.nist.gov/vuln/detail/CVE-2026-21877) | Authenticated RCE | Unsafe file handling allowing code execution through uploaded content |

> [!WARNING]
> SEG is not a patch for these vulnerabilities.
> It is an architectural approach designed to remove entire classes of unsafe execution patterns from automation workflows.

## 3. Key Features

- DSL-defined action model backed by YAML specs
- Immutable in-memory action registry built at startup from validated specs
- Runtime command rendering with typed params, flags, defaults, and output declarations
- Authenticated action discovery and execution through `/v1/actions`
- API-based file management through `/v1/files`
- SEG-managed file outputs for declared command outputs and optional sanitized stdout materialization via `stdout_as_file`
- Defense-in-depth middleware for auth, request integrity, rate limiting, timeouts, request IDs, and observability
- Runtime-aware OpenAPI generation with per-action examples and public contracts
- Rootless container deployment model
- Automated CI, security scanning, release, and API docs publication workflows

## 4. Architecture Overview

At runtime, requests move through a short and explicit pipeline:

```mermaid
flowchart TD
Client --> Middleware
Middleware --> Routes
Routes --> Registry
Registry --> Runtime
Runtime --> Execution
Runtime --> ManagedFiles
ManagedFiles --> Storage
```

The action system itself is layered:

```mermaid
flowchart LR
Specs[YAML specs] --> Loader
Loader --> Validator
Validator --> Builder
Builder --> Registry
Registry --> Presentation
Registry --> Renderer
Renderer --> Executor
Executor --> Outputs
```

For a full walkthrough, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 5. Security Model

SEG is designed around explicit controls rather than broad execution capabilities.

- Bearer token authentication on protected endpoints
- Request integrity validation at the ASGI boundary
- Immutable in-memory registry of DSL-defined actions compiled at startup
- Startup validation of DSL action spec files and semantic rules
- Binary allowlisting and blocklisting during action build and execution
- Filesystem storage rooted and sandboxed at `SEG_ROOT_DIR`
- Typed file management via `/v1/files` instead of direct path exposure
- Process-local rate limiting and per-request timeouts
- Request correlation and Prometheus metrics for auditability

An action ultimately becomes subprocess command execution, but only after SEG validates the DSL, validates request params, renders argv deterministically, enforces binary policy, and sanitizes outputs.

For the full threat analysis, see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## 6. Quick Start

SEG is designed to run inside Docker, stay reachable on the shared Docker network, and be published to localhost by default for local development and demos.

> [!IMPORTANT]
> Before starting the stack, create `secrets/seg_api_token.txt` and ensure the external Docker network named by `SHARED_DOCKER_NETWORK` exists.

Minimal local startup:

```bash
git clone https://github.com/Libertocrat/seg.git
cd seg

# Create the runtime configuration file from the template
# The ".env" file defines sandbox limits, runtime safeguards,
# and Docker infrastructure parameters used by the SEG container
cp .env.example .env
mkdir -p secrets
openssl rand -hex 32 > secrets/seg_api_token.txt

# Replace docker-network if you changed SHARED_DOCKER_NETWORK in .env
docker network create docker-network || true
docker compose up -d --build
```

Notes:

- by default, `docker-compose.yml` publishes SEG to `127.0.0.1:${SEG_HOST_PORT}`
- runtime configuration is defined by the environment variables set in `.env`
  - check the `.env.example` file for detailed information about env variables
- the container joins the external network defined by `SHARED_DOCKER_NETWORK`
- internal Docker consumers should use `http://seg:${SEG_PORT}`
- the external Docker network must exist before `docker compose up`
- `seg-init` prepares ownership and permissions on `SEG_ROOT_DIR` before `seg` starts
- the runtime API token is loaded from `secrets/seg_api_token.txt` through the Docker secret mount

Useful follow-up checks:

```bash
docker compose ps
docker compose logs -f
```

If host publishing is disabled in Compose and you still need temporary localhost access during development:

```bash
./scripts/seg-forward.sh --env-file .env
```

With the default Compose settings, SEG is available at:

- `http://localhost:8080`

Healthcheck:

```bash
curl http://localhost:8080/health
```

Docs are enabled by default:

- `http://localhost:8080/docs`

Set `SEG_ENABLE_DOCS=false` when the OpenAPI docs are not needed, especially in production deployments.

To publish SEG on a different host port, set `SEG_HOST_PORT` in `.env` (for example `SEG_HOST_PORT=8090`) and use `http://localhost:8090`.

By default, SEG binds to `127.0.0.1` on the host. To expose it on all host interfaces, set `SEG_HOST_BIND_ADDRESS=0.0.0.0` intentionally and ensure proper network controls.

The local development workflow is documented in [DEVELOPMENT.md](DEVELOPMENT.md).

## 7. Configuration

SEG runtime behavior is configured through environment variables defined in the local `.env` file. Docker Compose reads these variables and injects them into the container environment, where SEG validates and loads its runtime configuration at startup. Review [.env.example](.env.example) for the full documented list and detailed notes for every configurable variable.

```mermaid
flowchart LR
EnvFile[.env] --> Compose[Docker Compose]
EnvFile --> RuntimeEnv[Container Environment]
Compose --> SEG[SEG Container]
RuntimeEnv --> Settings[SEG Settings Validation]
Settings --> Runtime[SEG Runtime Configuration]
```

Values shown in `.env.example` are placeholder deployment values and do not necessarily represent application defaults or the configuration needed for your particular deployment environment.

### Important variables

| Variable | Description | Default |
| --- | --- | --- |
| `SEG_ROOT_DIR` | Absolute storage root used by SEG for managed blobs and metadata. | `/var/lib/seg` |
| `SEG_MAX_FILE_BYTES` | Maximum accepted upload size and file-processing size limit. | `104857600` |
| `SEG_MAX_YML_BYTES` | Maximum size for one DSL spec file. | `102400` |
| `SEG_MAX_STDOUT_BYTES` | Optional max stdout bytes returned from action execution. | unset |
| `SEG_MAX_STDERR_BYTES` | Optional max stderr bytes returned from action execution. | unset |
| `SEG_TIMEOUT_MS` | Per-request timeout in milliseconds. | `5000` |
| `SEG_RATE_LIMIT_RPS` | Process-local requests per second limit. | `10` |
| `SEG_APP_VERSION` | Version exposed by the runtime and OpenAPI metadata. | `0.1.0` |
| `SEG_ENABLE_DOCS` | Enables `/docs`, `/redoc`, and `/openapi.json`. Disable it when docs are not needed. | `true` |
| `SEG_ENABLE_SECURITY_HEADERS` | Enables baseline response security headers. | `true` |
| `SEG_BLOCKED_BINARIES_EXTRA` | Optional CSV of additional blocked binaries. | unset |
| `SHARED_DOCKER_NETWORK` | External Docker network used by the Compose deployment. | `docker-network` |
| `SEG_HOST_BIND_ADDRESS` | Host interface used by Compose when publishing SEG. | `127.0.0.1` |
| `SEG_HOST_PORT` | Host port used by Compose for localhost access. | `8080` |
| `SEG_PORT` | Internal listen port inside the container (reachable as `http://seg:8080`). | `8080` |

> [!IMPORTANT]
> When deploying SEG inside an existing container environment or microservice stack, the following variables should normally be reviewed and adapted before startup:
>
> - `SEG_ROOT_DIR`
> - `SHARED_DOCKER_NETWORK`
> - `COMPOSE_PROJECT_NAME`
> - `NON_ROOT_UID`
> - `NON_ROOT_GID`
>
> These variables control how SEG integrates with the Docker network, sandbox root, and storage permissions.

The API token is loaded from `/run/secrets/seg_api_token`, with `SEG_API_TOKEN_DEV` used only as a development fallback when the Docker secret is missing.

For container identity, runtime limits, timezone, and other deployment settings, see the complete reference in [.env.example](.env.example).

## 8. API Overview

SEG exposes a purposely small HTTP surface.

### Action endpoints

- `GET /v1/actions` lists available actions grouped by module, with optional `q` and `tag` filters
- `GET /v1/actions/{action_id}` returns the public contract for one DSL-defined action
- `POST /v1/actions/{action_id}` executes one action with a `params` payload and optional request-level execution options such as `stdout_as_file`

### File endpoints

- `POST /v1/files` uploads and persists a managed file
- `GET /v1/files` lists managed files with cursor pagination and optional filters
- `GET /v1/files/{id}` retrieves metadata by `file_id`
- `GET /v1/files/{id}/content` streams file content
- `DELETE /v1/files/{id}` deletes a managed file

### Public endpoints

- `GET /health`
- `GET /metrics`

Interactive and dynamically generated OpenAPI docs are enabled by default and can be disabled with `SEG_ENABLE_DOCS=false`:

- `/docs`
- `/redoc`
- `/openapi.json`

Hosted API documentation by release is published at:

- [SEG OpenAPI Docs](https://libertocrat.github.io/seg/api-docs)

> [!NOTE]
> This README intentionally does not document the current action catalog. The final public module and action set is still evolving.

## 9. Observability

SEG exports Prometheus-compatible metrics and request correlation metadata.

The `/metrics` endpoint includes request counters, duration histograms, inflight gauges, request integrity rejection counters, rate limit counters, and timeout counters. `X-Request-Id` is propagated or generated on every response.

## 10. Project Structure

The repository is organized around the application package, tests, documentation, and release tooling.

```text
seg/
|-- src/
|   `-- seg/
|       |-- actions/
|       |   |-- build_engine/    # YAML discovery, validation, and action compilation
|       |   |-- presentation/    # discovery payloads, contracts, and examples
|       |   |-- runtime/         # rendering, execution, sanitization, outputs
|       |   |-- schemas/         # DSL and module schema models
|       |   |-- specs/           # built-in YAML action specs
|       |   `-- registry.py      # immutable runtime registry
|       |-- core/                # config, errors, storage, security, openapi
|       |-- middleware/          # auth, integrity, observability, timeout, etc.
|       |-- routes/              # /v1/actions, /v1/files, /health, /metrics
|       `-- app.py               # FastAPI application factory
|-- tests/                       # smoke, unit, and integration tests
|-- docs/                        # architecture, testing, CI, and threat model docs
|-- scripts/                     # developer and release helper utilities
|-- requirements/                # runtime, testing, linting, security, and dev sets
|-- .github/workflows/           # CI, security, release, and docs publishing
|-- docker-compose.yml           # local container stack
|-- Dockerfile                   # container image build
|-- .env.example                 # runtime configuration template
`-- Makefile                     # local quality and security workflow entry point
```

## 11. Testing Strategy

The test suite combines smoke tests, unit tests, and integration tests.

Current coverage includes:

- DSL loader, validator, and builder behavior
- public action catalog, contracts, and serializers
- runtime renderer, executor, sanitizer, and output builders
- file upload, listing, metadata, download, and delete behavior
- settings validation and OpenAPI generation
- middleware enforcement and security-sensitive HTTP validation

For full test details, see [docs/TESTING.md](docs/TESTING.md).

## 12. CI / DevSecOps

SEG uses GitHub Actions plus a Makefile-driven local workflow for repeatable quality and security checks.

The repository includes these workflows:

- [CI quality gate](.github/workflows/ci.yml)
- [deep security workflow](.github/workflows/security.yml)
- [container release pipeline](.github/workflows/release.yml)
- [versioned API docs publishing pipeline](.github/workflows/release-docs.yml)

For details, see [docs/CI.md](docs/CI.md).

## 13. Documentation

Detailed design and workflow material lives in:

| Document | Description |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, DSL action pipeline, runtime execution, and OpenAPI design |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Threat model, trust boundaries, and mitigations |
| [docs/TESTING.md](docs/TESTING.md) | Testing strategy, fixtures, and local execution |
| [docs/CI.md](docs/CI.md) | CI, security scanning, release, and docs publication workflows |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local development environment and Makefile workflow |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Current contribution policy |
| [SECURITY.md](SECURITY.md) | Vulnerability disclosure policy |
| [scripts/README.md](scripts/README.md) | Developer and release helper scripts |

## 14. Development

Local development is documented in [DEVELOPMENT.md](DEVELOPMENT.md).

The main workflow is:

- define or edit DSL specs under `src/seg/actions/specs`
- run the container stack with Docker Compose
- validate behavior through tests and the authenticated action endpoints
- export and publish OpenAPI docs through the provided scripts and workflows

## 15. Contributing

External pull requests are currently paused while the project stabilizes its public API, security model, testing surface, and release process.

For the current policy, see [CONTRIBUTING.md](CONTRIBUTING.md).

## 16. Security Reporting

Do not report vulnerabilities in public issues.

Use the coordinated disclosure process documented in [SECURITY.md](SECURITY.md). For encrypted reporting, the repository includes [SECURITY_PGP_KEY.asc](SECURITY_PGP_KEY.asc).

## 17. License

SEG is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for the full text.

---
