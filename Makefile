.PHONY: help deps fmt lint typecheck hadolint test ci

PYTHON ?= python
PIP ?= pip

SRC_DIRS = src

help:
	@echo "make fmt        - Format code (black)"
	@echo "make lint       - Lint code (ruff + black --check)"
	@echo "make typecheck  - Type checking (mypy)"
	@echo "make hadolint   - Lint Dockerfile"
	@echo "make test       - Run tests (pytest)"
	@echo "make ci         - Run all checks"

deps:
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

fmt:
	black $(SRC_DIRS)

lint:
	black --check $(SRC_DIRS)
	ruff check $(SRC_DIRS)
typecheck:
	mypy --config-file mypy.ini $(SRC_DIRS)

hadolint:
	hadolint ./Dockerfile

test:
	pytest -q tests

ci: lint typecheck hadolint test
	@echo "All checks passed."