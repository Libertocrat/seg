.PHONY: help deps fmt lint typecheck hadolint test build ci pipeline

PYTHON ?= python
PIP ?= pip

# Include tests directory in formatting/linting/typechecking targets
SRC_DIRS = src tests

IMAGE_NAME ?= seg
IMAGE_TAG ?= local

help:
	@echo "make fmt        - Format code (black)"
	@echo "make lint       - Lint code (ruff + black --check)"
	@echo "make typecheck  - Type checking (mypy)"
	@echo "make hadolint   - Lint Dockerfile"
	@echo "make test       - Run tests (pytest)"
	@echo "make build      - Build Docker image locally"
	@echo "make ci         - Run all checks"
	@echo "make pipeline   - Run full local pipeline (ci + build)"

deps:
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

fmt:
	black $(SRC_DIRS)
	ruff check --fix $(SRC_DIRS)

lint:
	black --check $(SRC_DIRS)
	ruff check $(SRC_DIRS)

typecheck:
	mypy --config-file mypy.ini $(SRC_DIRS)

hadolint:
	hadolint ./Dockerfile

test:
	pytest -q tests

build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "Docker image $(IMAGE_NAME):$(IMAGE_TAG) built successfully."

ci: lint typecheck hadolint test
	@echo "All checks passed."

pipeline: ci build
	@echo "Full pipeline completed successfully."