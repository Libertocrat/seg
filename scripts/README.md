# Scripts

This directory contains helper scripts used for local development, release artifacts, and documentation publishing.

> [!IMPORTANT]
> Run the commands in this document from the repository root.

## Overview

| Script | Purpose |
| --- | --- |
| `scripts/init-shared-volume.sh` | Create and validate the Docker volume used as the SEG filesystem sandbox |
| `scripts/seg-forward.sh` | Forward a localhost port to a running SEG container without publishing ports in Compose |
| `scripts/export_openapi.py` | Build the FastAPI app and write the OpenAPI schema to disk |
| `scripts/build_docs_site.py` | Build a versioned Swagger UI site for GitHub Pages from the exported schema |

## init-shared-volume.sh

Initializes the shared Docker volume used by SEG and compatible services.

The script runs on the host, uses the Docker CLI, and applies filesystem changes inside a temporary `alpine:3.18` container mounted at `/data`.

### Responsibilities

- Create the Docker volume if it does not exist
- Configure group ownership and `setgid` permissions for the sandbox path
- Create allowed subdirectories when subdirectory sandbox mode is used
- Validate existing sandbox permissions before reuse

### Required configuration

The script accepts `--env-file <path>` or reads variables already exported in the environment.

Required variables:

- `SHARED_VOLUME_NAME`: Docker named volume to initialize
- `NON_ROOT_GID`: numeric group ID that must own the sandbox path
- `SEG_ALLOWED_SUBDIRS`: `*` for volume root access, or a comma-separated list such as `uploads,tmp`

If `--env-file` is provided, the required variables are loaded from that file. If `--env-file` is not provided, the required variables must already exist in the shell environment.

### Sandbox modes

- `SEG_ALLOWED_SUBDIRS="*"`: use `/data` as the sandbox root
- `SEG_ALLOWED_SUBDIRS="a,b,c"`: use `/data/a`, `/data/b`, `/data/c`

Subdirectory names must be simple names. Names containing `/`, `.` or `..` are rejected.

### Behavior

- New volumes are initialized with `root:<NON_ROOT_GID>` ownership and mode `2775`
- Existing volumes are validated for group ownership and `setgid`
- In subdirectory mode, missing allowed subdirectories are created
- Permission conflicts stop execution unless `--force` is provided
- `--dry-run` prints the Docker commands without changing the volume

### Flags

- `--env-file <path>`: load variables from a file
- `--dry-run`: print actions without executing them
- `--force`: apply permission fixes after conflict detection
- `-h`, `--help`: show usage and exit

### Example

```bash
./scripts/init-shared-volume.sh --env-file .env.example --dry-run
./scripts/init-shared-volume.sh --env-file .env.example
docker compose up -d
```

### Reference

- [scripts/specs/init-shared-volume.spec.md](scripts/specs/init-shared-volume.spec.md)

## seg-forward.sh

Creates a temporary localhost port forward to a running SEG container.

The script starts an ephemeral `alpine/socat` container on the same Docker network as SEG. The forward binds to `127.0.0.1`, not to all host interfaces.

### Responsibilities

- Resolve the target SEG container
- Choose or validate a local TCP port
- Start a temporary TCP forward to the SEG service port

### Required configuration

Required variables:

- `SHARED_DOCKER_NETWORK`: Docker network shared with SEG
- `SEG_PORT`: TCP port exposed by the SEG container
- `COMPOSE_PROJECT_NAME`: required only when `--container` is not provided

If `--env-file` is provided, the required variables are loaded from that file. If `--env-file` is not provided, the required variables must already exist in the shell environment.

### Container resolution

- If `--container <name>` is provided, that running container is used
- Otherwise the script searches for a running container whose name starts with `$COMPOSE_PROJECT_NAME-seg`
- Zero matches or multiple matches cause an error

### Local port selection

- `--local-port <port>` forces a specific port
- Without `--local-port`, the script scans ports `8081` through `8099`
- A port is considered unavailable if it is already listening on the host or already published by Docker

### Flags

- `--env-file <path>`: load variables from a file
- `--container <name>`: use a specific SEG container
- `--local-port <port>`: use a specific localhost port
- `--dry-run`: print actions without starting the proxy container
- `-h`, `--help`: show usage and exit

### Example

```bash
docker compose up -d seg
./scripts/seg-forward.sh --env-file .env.example
```

After the forward starts, the local URLs printed by the script include:

- `http://localhost:<PORT>/docs`
- `http://localhost:<PORT>/openapi.json`
- `http://localhost:<PORT>/health`

### Reference

- [scripts/specs/seg-forward.spec.md](scripts/specs/seg-forward.spec.md)

## export_openapi.py

Builds the SEG application and writes the generated OpenAPI schema to `docs/api-docs/output/openapi.json`.

### Responsibilities

- Normalize and validate the release version
- Build a documentation-specific `Settings` object
- Create the FastAPI application
- Generate and write the OpenAPI schema as JSON

### Inputs

- `RELEASE_VERSION`: optional environment variable
  - Accepted formats: `vX.Y.Z` or `X.Y.Z`
  - Default: `0.1.0`

### Behavior

- The script strips a leading `v` before storing the version in settings
- The generated settings enable docs endpoints during schema export
- The output directory is created automatically if needed
- The JSON file is written with indentation and a trailing newline

### Requirements

- Python dependencies required by SEG must be installed
- The SEG package must be importable in the current environment

### Example

```bash
export RELEASE_VERSION=v0.1.0
python scripts/export_openapi.py
```

Output:

- `docs/api-docs/output/openapi.json`

## build_docs_site.py

Builds a versioned Swagger UI site under `site/api-docs/` for publication to GitHub Pages.

### Responsibilities

- Create `site/api-docs/<RELEASE_VERSION>/`
- Copy Swagger UI static assets into the version directory
- Copy the repository Swagger template as `index.html`
- Copy the exported OpenAPI schema as `openapi.json`
- Create redirects for `site/index.html` and `site/api-docs/index.html`

### Inputs

- `RELEASE_VERSION`: required environment variable used as the version folder
- `docs/api-docs/template/swagger.html`: HTML template copied to the versioned site as `index.html`
- `docs/api-docs/output/openapi.json`: schema file produced by `scripts/export_openapi.py`
- `node_modules/swagger-ui-dist`: Swagger UI distribution copied into the site

### Behavior

- The script preserves existing content in `site/api-docs/` by copying new files into the selected version directory
- `site/api-docs/index.html` redirects to the latest version directory
- `site/index.html` redirects to `./api-docs/`

### Requirements

- `RELEASE_VERSION` must be set in the environment
- Swagger UI assets must already be installed under `node_modules`
- The OpenAPI export must already exist before this script runs

### Example

```bash
export RELEASE_VERSION=v0.1.0
npm init -y
npm install swagger-ui-dist@5.17.14
python scripts/export_openapi.py
python scripts/build_docs_site.py
```

Output:

- `site/api-docs/<RELEASE_VERSION>/index.html`
- `site/api-docs/<RELEASE_VERSION>/openapi.json`
- `site/api-docs/index.html`
- `site/index.html`

---
