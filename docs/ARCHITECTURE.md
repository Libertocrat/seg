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

### High-Level Flow

```text
CLIENT (n8n, CLI, SDK)
        │
        │ HTTP POST /v1/execute
        │
┌──────────────────────────────────────────────┐
│              FASTAPI ROUTE                   │
│  routes/commands.py                          │
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

---

### 4.3 Action

An **action** is a single, explicitly allowed operation that SEG can perform.

Examples (v1):

- `sha256_file`
- `mime_type`
- `file_stats`
- `delete_file`
- `move_file`

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

---

### 4.7 Security & Sanitization

All filesystem-related actions must pass through centralized security utilities:

- Path normalization and resolution
- Rejection of `..`, null bytes, and unsafe patterns
- Enforcement of `SEG_ALLOWED_SUBDIRS`
- Symlink rejection
- File size and timeout limits

Security helpers live in:

```text
core/security/
```

They are reused by all file-based and input sanitizing actions.

---

### 4.8 Composite Actions

Some actions (e.g. `file_stats`) are **composite actions**.

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
    commands.py

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
      sha256.py
      mime.py
      stat.py
      delete.py
      move.py
      io.py
      policy.py
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
