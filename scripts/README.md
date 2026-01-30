# Scripts

## init-shared-volume.sh

Initializes the shared Docker volume used by SEG and other internal services.

This script is a host-side initializer that prepares a Docker named volume to
act as a secure filesystem sandbox. All filesystem operations are executed
inside a temporary container (alpine:3.18); the script never mutates host
paths directly.

### Responsibilities

- Create the Docker volume if it does not exist
- Prepare deterministic group ownership and `setgid` semantics for the sandbox
- Create allowlisted subdirectories when configured

### Configuration source (.env)

The script accepts `--env-file <path>` or reads variables exported in the
environment. Use `.env.example` as a starting point.

Required variables (must be provided via the env file or exported):

- `SHARED_VOLUME_NAME`: Docker named volume to initialize
- `NON_ROOT_GID`: numeric GID that must own the sandbox directories
- `SEG_ALLOWED_SUBDIRS`: `*` for root sandbox or CSV list of simple subdir names (`uploads,outputs,temp`)

Optional variables (not required by the script, present for documentation):

- `NON_ROOT_UID`, `NON_ROOT_USER`, `NON_ROOT_GROUP`

### Behavior and guarantees

- The script distinguishes new vs existing volumes. New volumes are initialized
  deterministically; existing volumes are validated within the sandbox scope.
- `SEG_ALLOWED_SUBDIRS` is required. Use `*` to enable the volume root
  as the sandbox, or a CSV like `uploads,tmp` to limit the sandbox to those
  subdirectories. Empty or missing values cause an error.
- Conflicts are defined as group mismatch or missing setgid; the script exits
  on conflicts unless `--force` is provided, in which case it applies fixes.
- All filesystem changes are applied inside a single temporary container
  (`alpine:3.18`) mounted at `/data` to avoid host-side `chown`/`chmod`.

### Flags

- `--env-file <path>` — use the specified `.env` file as source of truth
- `--dry-run` — print the commands that would run without making changes
- `--force` — apply permission fixes when conflicts are detected
- `-h`, `--help` — show usage (must be used alone)

### Usage

Run this script before starting the Docker Compose stack.

```bash
./scripts/init-shared-volume.sh --env-file .env.example
docker compose up -d
```

### Notes

- The script uses the Docker CLI and therefore requires a user with Docker
  privileges on the host (this could be via membership in the `docker`
  group or using `sudo` depending on your environment).
- The initializer is idempotent and safe to run multiple times.

---

### Specification

The full technical specification and rationale for `init-shared-volume.sh` is
available in the repository: [scripts/specs/init-shared-volume.spec.md](scripts/specs/init-shared-volume.spec.md).

### Examples

- Dry-run using the example env file (no changes made):

```bash
./scripts/init-shared-volume.sh --env-file .env.example --dry-run
# Prints the docker run that would apply permissions and any checks.
```

- Initialize for real and then start compose (run as a user with Docker access):

```bash
./scripts/init-shared-volume.sh --env-file .env.example
docker compose up -d
# Prepares the named volume and then brings up services that mount it.
```

- Force-fix conflicts on an existing volume (careful — applies changes):

```bash
./scripts/init-shared-volume.sh --env-file .env.example --force
# If conflicts are detected (group mismatch / missing setgid) this fixes them.
```
