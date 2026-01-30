# init-shared-volume.sh - Technical Specification

## Purpose

`init-shared-volume.sh` is a host-side initialization script responsible for preparing
a shared Docker volume to be safely used as a filesystem sandbox by the
**Secure Execution Gateway (SEG)** and other compatible internal services.

The script enforces deterministic ownership, group-based access control, and
setgid semantics to guarantee consistent read/write behavior across containers
while minimizing privilege and blast radius.

---

## Scope & Responsibilities

The script has a **single responsibility**:

- Ensure a Docker named volume exists
- Prepare that volume to act as a secure filesystem sandbox

It explicitly **does NOT**:

- Start containers or Docker Compose stacks
- Create Docker networks
- Modify host filesystem paths directly
- Manage application-level authentication or authorization
- Perform runtime orchestration

---

## Execution Model

The script is executed **on the host** and uses Docker CLI commands to interact
with Docker-managed resources.

All filesystem operations inside the volume are performed via a **temporary
container**, never directly on the host filesystem.

---

## Supported Flags

| Flag | Description |
| ----- | ------------ |
| `--env-file <path>` | Path to a `.env` file used as the single source of truth |
| `--dry-run` | Print all actions without executing any state-changing commands |
| `--force` | Force permission fixes when conflicts are detected |
| `--help`, `-h` | Display usage information |

---

## Environment Variable Requirements

### Required Variables

These variables **must** be defined either via `--env-file` or already exported
in the environment:

| Variable | Description |
| -------- | ------------- |
| `SHARED_VOLUME_NAME` | Name of the Docker volume to initialize |
| `NON_ROOT_GID` | Target group ID used for shared access |
| `SEG_ALLOWED_SUBDIRS` | Defines the sandbox scope (see below) |

If any required variable is missing or empty, the script exits with an error.

---

## SEG_ALLOWED_SUBDIRS Semantics

`SEG_ALLOWED_SUBDIRS` defines **what part of the volume acts as the filesystem sandbox**.

### Supported Values

| Value | Meaning |
| ----- | -------- |
| `*` | Root sandbox — `/data` is the sandbox |
| `uploads,output,tmp` | Subdirectory sandbox — only listed subdirectories |
| *(unset)* | ❌ Invalid (error) |
| *(empty)* | ❌ Invalid (error) |

### Rules

- The value must be explicitly defined
- Empty values are rejected
- `*` is the **only** valid wildcard and must be used explicitly
- CSV values must contain only simple directory names (no paths)

---

## Sandbox Modes

The script operates in exactly one of two sandbox modes:

### Root Sandbox Mode (`SEG_ALLOWED_SUBDIRS=*`)

- The root of the volume (`/data`) is the sandbox
- Permissions and conflicts are evaluated on `/data`
- `/data` must be:
  - owned by `root:<NON_ROOT_GID>`
  - have setgid enabled (`2775`)

### Subdirectory Sandbox Mode (`SEG_ALLOWED_SUBDIRS=a,b,c`)

- Only listed subdirectories are part of the sandbox
- Root `/data` is ignored
- Each allowed subdirectory:
  - is created if missing
  - must be owned by `root:<NON_ROOT_GID>`
  - must have setgid enabled (`2775`)

---

## Volume Lifecycle Awareness

The script distinguishes between **new** and **existing** volumes.

### New Volume

- No conflict checks are performed
- Permissions are applied deterministically
- Allowlisted subdirectories are created as needed
- No warnings or errors are emitted

### Existing Volume

- Permissions are validated only within the sandbox scope
- Conflicts are detected only where SEG is allowed to operate
- Root `/data` is ignored unless in root sandbox mode

---

## Conflict Detection & Resolution

### What Is Considered a Conflict

A conflict occurs when:

- Group ownership does not match `NON_ROOT_GID`, or
- setgid bit is missing

Conflicts are evaluated:

- On `/data` in root sandbox mode
- On existing allowlisted subdirectories in subdir sandbox mode

### Conflict Handling Behavior

| Condition | Action |
| --------- | ------- |
| No conflicts | Continue |
| Conflicts + `--force` | Permissions are fixed |
| Conflicts without `--force` | Script exits with error |

---

## Dry-Run Mode (`--dry-run`)

When `--dry-run` is enabled:

- No Docker volumes are created
- No containers are started
- No images are pulled
- No filesystem changes are made

Instead:

- All intended commands are printed
- Configuration and validation logic still runs
- Output reflects the exact operations that would occur

---

## Container Execution Strategy

All filesystem operations are executed inside a **single temporary container**:

- Image: `alpine:3.18`
- Volume mounted at `/data`
- Shell commands constructed dynamically based on context

This guarantees:

- No direct host filesystem mutation
- No requirement for `sudo`
- Consistent behavior across Docker environments

---

## Security Properties

- Rootless execution inside application containers is enforced indirectly via GID
- setgid ensures files created by any compatible service remain group-accessible
- Explicit sandbox definition prevents accidental filesystem overreach
- No implicit defaults or unsafe fallbacks

---

## Idempotency

The script is fully idempotent:

- Safe to run multiple times
- Does not reapply permissions unnecessarily
- Deterministic outcomes across executions

---

## Intended Usage

This script is intended to be executed:

- Manually during environment setup
- As part of CI/CD pipelines
- Before running `docker-compose up`
- As a reusable volume initializer across microservices

---

## Non-Goals

- User management
- Network configuration
- Runtime service orchestration
- Dynamic policy evaluation

---

## Summary

`init-shared-volume.sh` provides a deterministic, explicit, and auditable mechanism
for preparing Docker volumes as secure shared sandboxes. Its design prioritizes:

- Security
- Explicit intent
- Idempotency
- Operational clarity

This script is suitable for production-grade environments and public repositories.
