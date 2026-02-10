# Continuous Integration (CI)

This document describes the Continuous Integration (CI) setup for the Secure Execution Gateway (SEG) project.

The CI pipeline enforces correctness, security invariants, and deterministic behavior across all supported environments (local development, Docker, and GitHub Actions).

---

## Goals

The CI system is designed to:

- Prevent regressions in security-critical code paths
- Enforce formatting, linting, and static typing
- Guarantee deterministic, isolated test execution
- Ensure no dependency on local `.env` files or developer machines
- Validate that the application can be built and executed safely
- Provide fast, actionable feedback on every pull request

---

## CI Entry Point

CI is driven by a **single source of truth**: the `Makefile`.

All checks executed in GitHub Actions can be reproduced locally with:

```bash
make ci
```

This guarantees parity between local development and CI.

---

## CI Pipeline Overview

The CI pipeline runs the following steps **in order**:

1. **Formatting check**

   - Tool: `black`
   - Command:

     ```bash
     black --check src tests
     ```

2. **Linting**

   - Tool: `ruff`
   - Command:

     ```bash
     ruff check src tests
     ```

3. **Static type checking**

   - Tool: `mypy`
   - Command:

     ```bash
     mypy --config-file mypy.ini src tests
     ```

4. **Dockerfile linting**

   - Tool: `hadolint`
   - Command:

     ```bash
     hadolint ./Dockerfile
     ```

5. **Test suite execution**

   - Tool: `pytest`
   - Command:

     ```bash
     pytest -q tests
     ```

All steps must pass for the CI job to succeed.

---

## GitHub Actions Workflow

The GitHub Actions workflow (`.github/workflows/ci.yml`) performs:

- Repository checkout
- Python setup (Python 3.12)
- System dependency installation
- Virtual environment creation
- Dependency installation
- Execution of `make ci`

The workflow intentionally mirrors the local workflow as closely as possible.

## Developer Quickstart (local CI parity)

Follow these steps to reproduce CI behavior locally on Linux:

```bash
# create and activate a virtual environment (Python 3.12)
python -m venv .venv
source .venv/bin/activate

# install runtime and dev dependencies
pip install --upgrade pip
pip install -r requirements.txt

# install pre-commit hooks
pip install pre-commit
pre-commit install

# install hadolint (example)
curl -sSL https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 \
  -o /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint

# run the CI pipeline locally (same order as CI)
make ci
```

This quickstart assumes a Linux environment and that system packages such as `libmagic` are available (see Tooling & system requirements below).

## Pre-commit policy

The project uses `pre-commit` to run fast, local checks before pushing changes. The configured hooks are:

- `black`: code formatter
- `ruff`: linter and local formatter
- `mypy`: static type checks
- `hadolint`: Dockerfile lint (local hook running system binary)
- `pytest`: test suite (configured as a local hook)

Notes & recommendations:

- `pre-commit` runs `black` and `ruff` on both `src/` and `tests/` (so tests are verified for formatting and lint rules locally). The `mypy` pre-commit hook is configured to type-check `src` and `tests` and includes test runtime dependencies to avoid missing-imports in isolated hook environments.

## Tooling & system requirements

Minimum tools required to reproduce CI locally (Linux):

- Python 3.12
- `make`
- `pip` and a virtualenv (`python -m venv`)
- `curl` (for optional hadolint installation)
- `hadolint` (Dockerfile linting): can be installed via the release binary or used via Docker image
- `libmagic` system library (provided by `libmagic1` / `libmagic-dev` on Debian/Ubuntu): required by `python-magic` runtime
- Build tools (`build-essential`) may be required to install some Python packages.

All developer instructions assume Linux hosts. Documented installation commands in this repo are examples; package names may vary across distributions.

---

## CI configuration files (where policies live)

The CI and local checks draw configuration from a small set of repository files. Reference these when you need to change formatting, linting, test settings, or pre-commit hooks:

- Formatting, linting and pytest configuration: [pyproject.toml](pyproject.toml)
  - `black` and `ruff` configuration blocks are defined here.
  - `pytest` settings used by local runs and some CI flows are under
    `[tool.pytest.ini_options]`.
- Pre-commit hooks: [.pre-commit-config.yaml](.pre-commit-config.yaml)
  - Lists the `black`, `ruff`, `mypy`, `hadolint` and `pytest` hooks and their settings.
- Canonical CI driver: [Makefile](Makefile)
  - The `ci` target orchestrates `lint`, `typecheck`, `hadolint`, and `test`.

Important: The `Makefile` is the canonical CI driver. If you change the sequence of checks or add/remove a step in CI, update the `ci` target in the `Makefile` first: GitHub Actions expects the same pipeline behavior.

When updating checks, prefer editing `pyproject.toml` and `.pre-commit-config.yaml` so local developer tooling and CI remain in sync.

### Tool versions & quick verification

The CI environment uses Python 3.12. To verify your local environment matches CI, run:

```bash
python --version
pip --version
```

To inspect installed package versions (useful when debugging mypy or pre-commit discrepancies):

```bash
pip freeze | grep -E "pydantic|fastapi|uvicorn|mypy|ruff|black"
```

Note: The `mypy` pre-commit hook defines `additional_dependencies` to ensure type-checking runs in an isolated environment. Keep those settings and `requirements.txt` reasonably aligned to avoid surprising differences between local pre-commit runs and CI.

---

## Test Isolation Guarantees

SEG enforces **strict configuration isolation** during tests.

### Environment isolation

- All environment variables starting with `SEG_` are removed before each test
- Tests must explicitly provide required configuration via fixtures
- Tests never rely on a developer’s local shell or CI environment

### `.env` handling

- Loading of `.env` files is explicitly disabled during tests
- This prevents accidental coupling between tests and local configuration
- CI failures caused by missing `.env` files are intentional and correct

### Result

If a test passes in CI, it is guaranteed to be:

- Deterministic
- Reproducible
- Independent of local machine state

---

## Application Factory Pattern

SEG uses an **application factory pattern** via:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    ...
```

### Why this matters

- Prevents configuration side effects at import time
- Allows tests to control configuration explicitly
- Enables proper isolation between runtime, CI, and tests
- Avoids implicit global state

### Important rule

> **The FastAPI application is never instantiated at import time.**

There is intentionally **no** global `app = create_app()` in the codebase.

---

## Runtime Invocation (Uvicorn)

Because SEG uses an application factory, the service must be started using
Uvicorn’s `--factory` mode.

### Local development

```bash
PYTHONPATH=./src \
uvicorn --factory seg.app:create_app \
  --host 0.0.0.0 \
  --port 8080 \
  --reload \
  --reload-dir src
```

### Docker runtime

The Docker image uses the same factory-based invocation:

```bash
uvicorn --factory seg.app:create_app \
  --host 0.0.0.0 \
  --port ${SEG_PORT}
  --proxy-headers
```

This removes Uvicorn startup warnings and makes the intended startup model
explicit and unambiguous.

---

## CI Philosophy

CI in SEG is intentionally strict.

If CI fails, it usually indicates one of the following:

- A missing or implicit configuration dependency
- A security invariant violation
- A regression in contract or behavior
- An environment-specific assumption leaking into tests

This is by design.

CI is treated as a **first-class security and correctness gate**, not a
best-effort check.

---

## Summary

- CI is deterministic, isolated, and reproducible
- Tests never depend on `.env` or local configuration
- The Makefile is the canonical CI interface
- SEG uses an explicit FastAPI application factory
- Runtime, Docker, and CI all use the same startup model

If CI passes, the system is considered safe to run and extend.

---
