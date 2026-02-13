# SEG - Architecture Specification

**Status:** Frozen (v1)  
**Audience:** Developers, reviewers, GitHub Copilot  
**Scope:** SEG v1 (file-related secure actions)

---

## 1. Purpose

SEG (Secure Execution Gateway) is a hardened FastAPI-based microservice designed to safely execute a **strictly limited and explicitly allowed set of filesystem-related actions** on behalf of upstream systems (e.g. n8n workflows).

SEG is intentionally **not a generic execution engine**.  
It is a controlled capability gateway with strong boundaries, explicit policies, and a stable external contract.

The primary goals are:

- Minimize blast radius when executing potentially dangerous operations
- Provide a stable, machine-friendly API contract
- Allow controlled extensibility via explicit action registration
- Be suitable for production use and security-focused portfolios

---

## 2. Non-Goals (v1)

SEG v1 explicitly does **not** aim to:

- Execute arbitrary shell commands
- Support dynamic plugin loading
- Implement role-based access control per action
- Provide multi-tenant isolation
- Act as a general-purpose workflow engine

These are intentionally out of scope.

---

## 3. High-Level Architecture

SEG follows a layered architecture with a strict separation between:

- HTTP / framework concerns (FastAPI)
- Boundary schemas (stable API contract)
- Action dispatch and execution (project-specific)
- Security and filesystem hardening
  - Shared mounted sandbox directory (`SEG_SANDBOX_DIR`)

### High-Level Flow

```text
CLIENT (n8n, CLI, SDK)
        │
        │ HTTP POST /v1/execute
        │
┌──────────────────────────────────────────────┐
│              FASTAPI ROUTE                   │
│  routes/execute.py                           │
│                                              │
│  - Receives HTTP                             │
│  - Validates ExecuteRequest                  │
│  - No business logic                         │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│           BOUNDARY SCHEMAS                    │
│                                              │
│  ExecuteRequest                               │
│  ResponseEnvelope                             │
│  ErrorInfo                                   │
│                                              │
│  (core/schemas/*)                             │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│          ACTION FRAMEWORK (SEG)              │
│                                              │
│  Dispatcher                                  │
│   - Resolves action                           │
│   - Validates params                          │
│   - Executes handler                          │
│                                              │
│  Registry                                    │
│   - Explicit allowlist of actions             │
│                                              │
│  Handler                                     │
│   - Implements one action                     │
│   - Applies security & policy                 │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│         RESPONSE ENVELOPE                    │
└──────────────────────────────────────────────┘
        │
        ▼
CLIENT RESPONSE
```

---

## 4. Core Concepts

### 4.1 Route (FastAPI)

- Defines HTTP endpoints
- Performs request/response validation
- Must not contain business logic
- Delegates execution to the dispatcher

Example:

- `POST /v1/execute`

---

### 4.2 Boundary Schemas

Boundary schemas define the **stable public API contract**.

They are versioned implicitly by the API path (e.g. `/v1`) and must remain stable across internal refactors.

Examples:

- `ExecuteRequest`
- `ResponseEnvelope`
- `ErrorInfo`

Boundary schemas live in:

```text
core/schemas/
```

#### Note on action schemas (pattern)

- Action-specific schemas (both `params` and `result`) are colocated with the action implementation under `src/seg/actions/<action>/` (or in a per-action `schemas` module). This keeps the contract next to the code that implements it and makes evolving an action independent from core schema churn.

  Example layout:

  ```text
  src/seg/actions/file/
    checksum.py         # handler implementation
    schemas.py          # ChecksumParams / ChecksumResult Pydantic models
  ```

- The `ActionSpec` registered in the `registry` references the `params_model` (Pydantic) and the `result_model` (Pydantic). The dispatcher performs validation by calling `params_model.model_validate()` so handlers receive well-typed models instead of raw dicts.

#### Note on runtime action discovery

For the `seg.actions.discover_and_register` function to automatically discover and import action modules at runtime, each action subdirectory must be a Python package (contain an `__init__.py`) and action modules must be importable by module name (for example `seg.actions.file.checksum`). We also recommend explicitly exporting submodules or handlers from the package `__init__.py` (for example `from . import checksum`) to ensure that importing the package triggers the registration side-effect (`register_action`). If a package or module is not importable, the action will not be registered and will not be available to `/v1/execute`.

---

### 4.3 Action

An **action** is a single, explicitly allowed operation that SEG can perform.

Examples (v1):

- `file_checksum`
- `file_mime_detect`
- `file_stat`
- `file_delete`
- `file_move`

Actions are:

- Named explicitly
- Whitelisted via the registry
- Executed only through the dispatcher

---

### 4.4 Handler

A **handler** is the concrete implementation of an action.

Responsibilities:

- Validate and sanitize inputs
- Enforce filesystem and security policies
- Perform the actual operation
- Return structured data (no HTTP responses)

Handlers:

- Are unaware of FastAPI
- Do not return status codes
- Do not raise raw HTTP exceptions

---

### 4.5 Dispatcher

The dispatcher is the central orchestrator of actions.

Responsibilities:

- Receive `action` and `params`
- Resolve the correct handler via the registry
- Validate params against the correct Pydantic model
- Execute the handler
- Normalize errors into structured failures

The dispatcher is **framework-agnostic** and contains no HTTP logic.

Implementation notes:

- The dispatcher accepts an `ExecuteRequest`, looks up the action in the registry, validates `params` using the action's `params_model`, and calls the handler with the validated model. It returns the handler's result (a Pydantic model or plain dict) to the route layer which is responsible for converting it into the `ResponseEnvelope`.
- Handlers are allowed to raise small domain exceptions; the route layer or a small adapter maps those to stable `ErrorInfo.code` values and HTTP status codes.

---

### 4.6 Registry

The registry is an explicit mapping of:

```text
action_name → handler
```

Its purpose is to:

- Enforce a strict allowlist
- Avoid dynamic or reflective execution
- Make supported capabilities auditable

Actions must be registered explicitly to be executable.

ActionSpec (registry shape)

- Each registered action exposes an `ActionSpec` containing:
  - `name`: action name (string)
  - `params_model`: Pydantic model class used to validate `params`
  - `result_model`: Pydantic model class describing the action result (optional)
  - `handler`: an async callable that accepts the validated params model

This explicit shape allows the dispatcher to remain tiny and lets the
registry serve as the single source of truth for supported actions.

Action metadata endpoint

- To expose action contracts to clients and to aid documentation, the service provides a machine-readable endpoint `GET /v1/actions` that returns the list of registered actions and, for each action, the JSON chema produced by the action's `params_model` (and examples when available). This preserves a single runtime endpoint (`/v1/execute`) while enabling discoverability and automated documentation.

---

### 4.7 Security & Sanitization

All filesystem-related actions must pass through centralized security utilities:

- Path normalization and resolution
- Rejection of `..`, null bytes, and unsafe patterns
- Enforcement of `SEG_SANDBOX_DIR` and `SEG_ALLOWED_SUBDIRS`
- Symlink rejection
- File size and timeout limits

Security helpers live in:

```text
core/security/
```

They are reused by all file-based and input sanitizing actions.

OpenAPI documentation endpoints are disabled by default and are controlled at runtime via the environment variable `SEG_ENABLE_DOCS` (default: `false`). Enable the docs only for local debugging or trusted environments; keep `SEG_ENABLE_DOCS=false` in production to avoid exposing interactive API endpoints.

---

### 4.8 Composite Actions

Some actions (e.g. `file_stat`) are **composite actions**.

They:

- Reuse existing handlers internally
- Do not introduce new low-level operations
- Reduce round-trips for clients

Composite actions validate that the architecture supports orchestration without duplication.

---

## 5. Filesystem Layout (General)

```text
src/seg/
  app.py

  routes/
    health.py
    metrics.py
    execute.py

  core/
    config.py
    exceptions.py
    schemas/
      envelope.py
      execute.py
      actions/
        file.py
    security/
      paths.py
      validation.py

  actions/
    registry.py
    dispatcher.py
    errors.py
    types.py
    file/
      checksum.py
      mime.py
      stat.py
      delete.py
      move.py
      io.py
      policy.py
      schemas.py
```

---

## 6. Design Principles

- Explicit > implicit
- Allowlist > blocklist
- Boundaries are more important than features
- HTTP is not business logic
- Security failures must be explicit and structured
- Extensibility without dynamic execution

---

## 7. Versioning Strategy

- External API versioning via path (`/v1`)
- Boundary schemas are stable within a version
- Internal handlers and policies may evolve freely

---

## 8. Summary

SEG is designed as a **secure capability gateway**, not a generic execution service.

The architecture prioritizes:

- Safety
- Clarity
- Auditability
- Real-world production use

The v1 feature set is intentionally small and complete, serving as a foundation for future extensions without compromising security guarantees.

---
