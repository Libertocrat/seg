#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# init-shared-volume.sh
#
# Host-side initializer for a shared Docker volume.
#
# Responsibilities:
# - Create the Docker volume if it does not exist
# - Enforce group ownership and setgid permissions
# - Prepare filesystem sandbox for SEG and compatible services
#
# Required variables (via --env-file or exported):
#   - SHARED_VOLUME_NAME
#   - NON_ROOT_GID
#   - SEG_ALLOWED_SUBDIRS
#
# SEG_ALLOWED_SUBDIRS semantics:
#   - "*"              → root sandbox (/data)
#   - "a,b,c"          → subdirectory sandbox
#   - empty / missing  → ERROR
#
# Supported flags:
#   --env-file <path>   Load variables from a .env file
#   --dry-run           Show actions without executing
#   --force             Force permission fixes on conflicts
# -----------------------------------------------------------------------------

SCRIPT_NAME="$(basename "$0")"

DRY_RUN=false
FORCE=false
ENV_FILE=""

CONFLICT_EXIT_CODE=42

# -----------------------------------------------------------------------------
# Helper functions
log()   { echo "[INFO] $*"; }
warn()  { echo "[WARN] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

run() {
  # Execute command safely without eval. Arguments should be passed as
  # separate words to "run" (e.g. run docker volume create "name").
  if $DRY_RUN; then
    printf '[DRY-RUN] '
    printf '%q ' "$@"
    echo
    return 0
  fi

  "$@"
}

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME [--env-file <path>] [--dry-run] [--force]

Description:
  Initializes a shared Docker volume and enforces group-based permissions.

Behavior notes:
  - If --env-file is provided the file is the single source of truth and
    must contain the required keys (SHARED_VOLUME_NAME, NON_ROOT_GID, SEG_ALLOWED_SUBDIRS).
  - If --env-file is NOT provided the script expects these variables to be
    exported in the environment (suitable for CI/CD).

Options:
  --env-file <path>   Path to .env file (explicit; required values must exist inside)
  --dry-run           Print actions without executing
  --force             Force recursive chown/chmod if conflicts exist
  -h, --help          Show this help
EOF
}

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------

# If --help/-h appears, enforce exclusivity: it must be used alone.
for _a in "$@"; do
  if [[ "$_a" == "-h" || "$_a" == "--help" ]]; then
    if [[ $# -gt 1 ]]; then
      error "--help/-h must be used alone; no other flags allowed"
    fi
    usage
    exit 0
  fi
done

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --env-file)
      shift
      [[ $# -eq 0 ]] && error "--env-file requires a path argument"
      [[ "$1" == --* ]] && error "--env-file requires a path argument, got flag: $1"
      ENV_FILE="$1"
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      error "Unknown argument: $1"
      ;;
  esac
done

# If you don't accept positional args, fail fast:
if [[ $# -gt 0 ]]; then
  error "Unexpected positional arguments: $*"
fi

# -----------------------------------------------------------------------------
# Preconditions
# -----------------------------------------------------------------------------

command -v docker >/dev/null 2>&1 || error "Docker CLI not found. Is Docker installed?"

REQUIRED_VARS=(
  SHARED_VOLUME_NAME
  NON_ROOT_GID
  SEG_ALLOWED_SUBDIRS
)

if [[ -n "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" ]] || error "Env file not found: $ENV_FILE"
  log "Loading environment from $ENV_FILE"

  # Ensure required vars come ONLY from the env file
  for var in "${REQUIRED_VARS[@]}"; do
    unset "$var"
  done

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  log "No --env-file provided; expecting required variables exported in the environment"
fi

# Validate required variables
missing_vars=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing_vars+=("$var")
  fi
done

if (( ${#missing_vars[@]} > 0 )); then
  error "Missing required variables: ${missing_vars[*]}"
fi

if [[ -z "$SEG_ALLOWED_SUBDIRS" ]]; then
  error "SEG_ALLOWED_SUBDIRS is empty. Use '*' to explicitly enable root sandbox access."
fi

# -----------------------------------------------------------------------------
# Resolve sandbox mode
# -----------------------------------------------------------------------------

if [[ "$SEG_ALLOWED_SUBDIRS" == "*" ]]; then
  SANDBOX_MODE="root"
  log "Sandbox mode: ROOT (volume root dir)"
else
  SANDBOX_MODE="subdirs"
  IFS=',' read -ra ALLOWED_SUBDIRS <<< "$SEG_ALLOWED_SUBDIRS"
  log "Sandbox mode: SUBDIRS (${ALLOWED_SUBDIRS[*]})"
fi

# -----------------------------------------------------------------------------
# Create volume if missing (track new vs existing)
# -----------------------------------------------------------------------------

VOLUME_IS_NEW=false

if ! docker volume inspect "$SHARED_VOLUME_NAME" >/dev/null 2>&1; then
  log "Docker volume '$SHARED_VOLUME_NAME' does not exist. Creating."
  VOLUME_IS_NEW=true
  run docker volume create "$SHARED_VOLUME_NAME"
else
  log "Docker volume '$SHARED_VOLUME_NAME' already exists."
fi

# -----------------------------------------------------------------------------
# Sandbox preparation & permission enforcement
# -----------------------------------------------------------------------------

CONTAINER_CMD="set -e"

if [[ "$SANDBOX_MODE" == "root" ]]; then
  if $VOLUME_IS_NEW; then
    log "Initializing root sandbox permissions (new volume)"
    CONTAINER_CMD+="
      chown root:${NON_ROOT_GID} /data &&
      chmod 2775 /data
    "
  else
    log "Validating root sandbox permissions (existing volume)"
    CONTAINER_CMD+="
      if [ \"\$(stat -c %g /data)\" != \"${NON_ROOT_GID}\" ]; then
        echo 'Conflict: /data group mismatch'
        exit $CONFLICT_EXIT_CODE
      fi
      if ! stat -c %A /data | grep -q s; then
        echo 'Conflict: setgid not set on /data'
        exit $CONFLICT_EXIT_CODE
      fi
    "
    if $FORCE; then
      CONTAINER_CMD+="
        chown root:${NON_ROOT_GID} /data &&
        chmod 2775 /data
      "
    fi
  fi

else
  for subdir in "${ALLOWED_SUBDIRS[@]}"; do
    subdir="$(echo "$subdir" | xargs)"
    [[ -z "$subdir" ]] && continue

    [[ "$subdir" == */* || "$subdir" == "." || "$subdir" == ".." ]] && \
      error "Invalid subdirectory name: $subdir"

    if $VOLUME_IS_NEW; then
      log "Creating sandbox subdir: $subdir"
      CONTAINER_CMD+="
        mkdir -p /data/${subdir} &&
        chown root:${NON_ROOT_GID} /data/${subdir} &&
        chmod 2775 /data/${subdir}
      "
    else
      log "Validating sandbox subdir: $subdir"
      CONTAINER_CMD+="
        if [ -d /data/${subdir} ]; then
          if [ \"\$(stat -c %g /data/${subdir})\" != \"${NON_ROOT_GID}\" ]; then
            echo 'Conflict: ${subdir} group mismatch'
            exit $CONFLICT_EXIT_CODE
          fi
          if ! stat -c %A /data/${subdir} | grep -q s; then
            echo 'Conflict: setgid not set on ${subdir}'
            exit $CONFLICT_EXIT_CODE
          fi
        else
          mkdir -p /data/${subdir} &&
          chown root:${NON_ROOT_GID} /data/${subdir} &&
          chmod 2775 /data/${subdir}
        fi
      "
      if $FORCE; then
        CONTAINER_CMD+="
          chown root:${NON_ROOT_GID} /data/${subdir} &&
          chmod 2775 /data/${subdir}
        "
      fi
    fi
  done
fi

if $DRY_RUN; then
  log "[DRY-RUN] docker run --rm -v ${SHARED_VOLUME_NAME}:/data alpine:3.18 sh -c \"$CONTAINER_CMD\""
else
  if ! docker run --rm -v "${SHARED_VOLUME_NAME}:/data" alpine:3.18 sh -c "$CONTAINER_CMD"; then
    if ! $FORCE; then
      error "Permission conflicts detected. Re-run with --force to apply fixes."
    fi
  fi
fi

log "Shared volume initialization completed successfully."
