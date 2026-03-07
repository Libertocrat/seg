# Contributing

Thank you for your interest in contributing to the Secure Execution Gateway (SEG).

Current status: this repository is NOT accepting external contributions at the moment.

Reason: the project is in its initial architecture and implementation phase. We want to stabilize the API, tests, and security posture before opening the project for external contributions.

Future: once the project reaches a stable release and we have CI, tests, and review processes in place, we will publish contribution guidelines (branching model, style guide, and pull request process).

In the meantime, if you have feedback, improvement ideas, or security reports, please contact the project maintainer (see [SECURITY.md](SECURITY.md)).

Note: do NOT open public issue tracker entries for security vulnerabilities; follow the guidance in [SECURITY.md](SECURITY.md) for private disclosure.

Thank you for your understanding.

## Developer Quickstart

This repository assumes a Linux development environment. The sections below provide the minimal steps to prepare a developer workstation to run linters, tests and reproduce the CI checks locally.

0. Set local Python development version to 3.12:

```bash
pyenv versions | grep 3.12 # Verify pyenv and py 3.12 are installed
pyenv install 3.12
pyenv local 3.12
```

1. Create and activate a Python virtual environment:

```bash
python --version # Verify its 3.12 before proceeding
python -m venv .venv
source .venv/bin/activate
```

2. Install Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

3. (Optional) Install tooling used by CI and pre-commit hooks:

```bash
# Debian/Ubuntu example (requires sudo)
sudo apt-get update
sudo apt-get install -y make curl libmagic1 build-essential

# Install hadolint (example):
curl -sSL https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 \
	-o /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint
```

4. Install and enable `pre-commit` (recommended):

```bash
python -m pip install pre-commit
pre-commit install
```

5. Run CI locally:

```bash
make ci
```

6. Run the full pipeline locally (ci + build):

```bash
make pipeline
```

7. Run the pre-commit locally:

```bash
pre-commit run --all-files
```

Notes:

- The project CI uses Python 3.12. The repository assumes a Linux host for developer instructions (Windows is not documented at this time).
- If you encounter mypy cache issues after refactors, remove `.mypy_cache` and re-run the checks: `rm -rf .mypy_cache && make ci`.

### Quick commands (individual checks)

Run a single check locally when iterating quickly:

```bash
# Format
black src tests

# Lint and auto-fix formatting/import-order issues with ruff
ruff check --fix src tests

# Static typing
mypy --config-file mypy.ini src tests

# Run tests
pytest -q tests

# Run integration tests only
pytest -q tests/integration
```

Quick environment verification:

```bash
python --version
pip --version
pip freeze | grep -E "pydantic|fastapi|uvicorn|mypy|ruff|black"
```
