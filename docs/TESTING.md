# Testing Strategy

This document describes the testing philosophy, structure, and guarantees of the Secure Execution Gateway (SEG) project.

Testing in SEG is not treated as a coverage exercise, but as a **security and correctness contract**. Tests are designed to freeze invariants and prevent regressions in configuration, sandboxing, and execution behavior.

---

## Goals

The testing strategy is designed to:

- Freeze security invariants (sandbox boundaries, symlink handling, path validation)
- Guarantee deterministic and reproducible test execution
- Prevent coupling to developer machines or CI environments
- Validate request/response contracts and error behavior
- Enable confident extension of SEG with new actions and features

---

## Core Principles

### 1. Determinism over Coverage

SEG prioritizes **meaningful invariants** over artificial coverage metrics.

A test exists only if it protects one of the following:

- Security boundaries
- Configuration correctness
- API contracts
- Execution wiring

---

### 2. Strict Environment Isolation

Tests must never depend on:

- A local `.env` file
- Shell environment variables
- CI-provided configuration
- Import-time side effects

If a test requires configuration, it must be provided **explicitly via fixtures**.

---

### 3. No Import-Time Execution

SEG follows a strict rule:

> **Application code must not execute at import time.**

As a result:

- The FastAPI app is created via an application factory (`create_app`)
- No global `app = create_app()` exists
- Tests import code safely without triggering configuration loading

This is critical for test isolation and CI reliability.

---

## Configuration Isolation

SEG enforces **hard isolation** for configuration during tests.

### Environment handling

- All `SEG_*` environment variables are removed before each test
- `.env` loading is explicitly disabled
- Tests must set required variables explicitly

This guarantees that:

- CI failures are real failures
- Tests do not pass “by accident” on a developer machine
- Missing configuration is detected early

---

## Global Test Fixtures

SEG defines a small number of **global, test-only fixtures** in `conftest.py` that are automatically applied to all tests.

These fixtures are part of the testing architecture and are critical for deterministic and secure test execution.

---

### `clean_seg_environment` (autouse)

This fixture is applied automatically to **every test**.

Its responsibility is to enforce **strict configuration isolation** by:

- Removing all `SEG_*` variables from the process environment
- Disabling `.env` file loading in `Settings`
- Clearing the cached settings instance returned by `get_settings()`

#### Why this fixture exists

SEG settings are:

- Loaded lazily
- Resolved from environment variables
- Cached for performance and consistency

Without clearing the cache and environment before each test:

- Environment changes performed by fixtures would not take effect
- Tests could become order-dependent
- Local `.env` files could silently affect CI behavior

This fixture guarantees that:

- No test depends on developer or CI `.env` files
- No test depends on execution order
- Every test observes a fresh and explicit configuration state

#### Scope and constraints

- This fixture is **test-only**
- It MUST NOT be used in production code
- Any test requiring configuration must explicitly provide it via fixtures

Breaking this rule is considered a test bug.

---

### Other Common Fixtures

In addition to `clean_seg_environment`, SEG provides reusable fixtures such as:

- `minimal_safe_env`: provides the minimal required SEG configuration
- `sandbox_dir`: creates an isolated filesystem sandbox
- `api_token`: provides a deterministic authentication token
- `sandbox_file_factory`: helper to create files inside an allowed sandbox subdirectory for tests. Use this fixture to create deterministic test files inside the allowlisted subdirectory (it returns a Path for the created file).

These fixtures are the **only supported mechanism** for providing configuration to tests.

For implementation reference, see the test fixtures at [tests/conftest.py](../tests/conftest.py).

---

## Test Categories

### 1. Unit Tests

Unit tests validate isolated components without involving FastAPI or I/O.

Examples:

- `Settings` validation and defaults
- Schema validation (`ExecuteRequest`, `ResponseEnvelope`)
- Path sanitization and sandbox resolution
- Action logic (checksum, delete, etc.)

These tests are fast, deterministic, and require no network or server.

---

### 2. Security Tests

Security tests freeze the invariants that define SEG’s sandbox model.

They verify that SEG:

- Never escapes its sandbox directory
- Never follows symlinks (even if allowlisted)
- Rejects traversal attempts and malformed paths
- Enforces allowlists correctly
- Rejects unsafe filesystem operations

Security tests are intentionally strict and fail loudly.

---

### 3. Contract Tests

Contract tests validate stable API and data shapes.

Examples:

- Response envelope structure:

  ```json
  { "success": true, "data": ..., "error": null }
  ```

- Error responses:

  ```json
  { "success": false, "data": null, "error": {...} }
  ```

These tests ensure backward compatibility and predictable client behavior.

---

### 4. Integration Tests (FastAPI)

Integration tests validate that components are wired correctly:

- Middleware execution order
- Authentication behavior
- Endpoint routing
- Dispatcher and registry integration

These tests use FastAPI’s `TestClient` and a controlled test configuration.

---

### 5. Future: Container-Level Integration Tests

Planned tests include:

- Running SEG inside a Docker container
- Using a runner container on the same network
- Issuing real HTTP requests (`curl`-style)
- Validating health, execution, and sandbox behavior

These tests will likely use `docker-compose` and run as a CI stage.

---

## Fixtures Philosophy

Fixtures are the **only supported way** to provide configuration in tests.

Common fixtures include:

- `minimal_safe_env` – provides required SEG variables
- `sandbox_dir` – creates a temporary sandbox directory
- `api_token` – deterministic authentication token

Fixtures override the environment, not application code.

---

## What SEG Does *Not* Test (By Design)

SEG intentionally does **not** test:

- Uvicorn internals
- FastAPI framework behavior
- Docker runtime correctness
- OS-specific kernel behavior

These are treated as trusted dependencies.

---

## Failure Philosophy

A failing test usually means one of the following:

- A security invariant was violated
- A configuration dependency leaked into code
- An import-time side effect was introduced
- A contract changed unintentionally

Tests are expected to fail early and loudly.

---

## Summary

- Tests protect security and correctness, not metrics
- Configuration is explicit and isolated
- No import-time side effects are allowed
- Application factory pattern is mandatory
- Tests are designed to scale with new actions and features

If tests pass, SEG is considered safe to extend.

---
