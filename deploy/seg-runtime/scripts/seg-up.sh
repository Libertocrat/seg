#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers/common.sh
source "${SCRIPT_DIR}/helpers/common.sh"

# CLI mode flags with startup-safe defaults.
PULL_MODE=false
WAIT_MODE=true
SILENT_MODE=false

# Print CLI usage and examples.
usage() {
	cat <<'EOF'
Usage:
	seg-up.sh [options]

Description:
	Starts the SEG runtime stack using the generated .env file and local secret.

Options:
	--pull       Pull the configured SEG image before starting.
	--no-wait    Do not wait for /health after starting containers.
	--dry-run    Print commands without executing them.
	--silent     Suppress normal stdout output. Warnings and errors still go to stderr.
	-h, --help   Show this help.

Examples:
	./scripts/seg-up.sh
	./scripts/seg-up.sh --pull
	./scripts/seg-up.sh --no-wait
	./scripts/seg-up.sh --silent
	./scripts/seg-up.sh --dry-run
EOF
}

# Parse CLI flags for pull/wait/dry-run/silent startup behavior.
parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--pull)
				PULL_MODE=true
				shift
				;;
			--no-wait)
				WAIT_MODE=false
				shift
				;;
			--dry-run)
				DRY_RUN=true
				export DRY_RUN
				shift
				;;
			--silent)
				SILENT_MODE=true
				shift
				;;
			-h|--help)
				usage
				exit 0
				;;
			*)
				error "Unknown argument: $1"
				usage
				exit 1
				;;
		esac
	done
}

# Reject unsupported CLI combinations early.
validate_cli_flags() {
	if [[ "${DRY_RUN:-false}" == "true" && "${SILENT_MODE}" == "true" ]]; then
		die "--dry-run and --silent cannot be used together."
	fi
}

# Silent-mode wrappers: normal stdout output is suppressed when requested.
say_info() {
	[[ "${SILENT_MODE}" == "true" ]] && return 0
	info "$@"
}

say_success() {
	[[ "${SILENT_MODE}" == "true" ]] && return 0
	success "$@"
}

say_section() {
	[[ "${SILENT_MODE}" == "true" ]] && return 0
	section "$@"
}

say_step() {
	[[ "${SILENT_MODE}" == "true" ]] && return 0
	step "$@"
}

# Run Docker Compose commands while honoring dry-run and silent mode.
compose_quiet_if_silent() {
	if [[ "${SILENT_MODE}" == "true" ]]; then
		compose "$@" >/dev/null
	else
		compose "$@"
	fi
}

# Require a runtime env variable to be present and non-empty.
require_runtime_env_value() {
	local name="${1:?name is required}"
	local value="${!name-}"

	if ! is_non_empty "${value}"; then
		die "Missing required runtime variable: ${name}"
	fi
}

# Validate runtime env values loaded from the generated .env file.
validate_runtime_env() {
	require_runtime_env_value SEG_SHARED_NETWORK
	require_runtime_env_value SEG_DATA_VOLUME
	require_runtime_env_value SEG_IMAGE
	require_runtime_env_value SEG_HOST_BIND_ADDRESS
	require_runtime_env_value SEG_HOST_PORT
	require_runtime_env_value SEG_PORT
	require_runtime_env_value SEG_ROOT_DIR

	if ! is_safe_docker_name "${SEG_SHARED_NETWORK}"; then
		die "SEG_SHARED_NETWORK must use letters, numbers, dots, underscores or dashes. Current value: ${SEG_SHARED_NETWORK}"
	fi

	if ! is_safe_docker_name "${SEG_DATA_VOLUME}"; then
		die "SEG_DATA_VOLUME must use letters, numbers, dots, underscores or dashes. Current value: ${SEG_DATA_VOLUME}"
	fi

	if ! is_non_empty "${SEG_IMAGE}"; then
		die "Missing required runtime variable: SEG_IMAGE"
	fi

	if ! is_bind_address "${SEG_HOST_BIND_ADDRESS}"; then
		die "SEG_HOST_BIND_ADDRESS is invalid. Current value: ${SEG_HOST_BIND_ADDRESS}"
	fi

	if ! is_port "${SEG_HOST_PORT}"; then
		die "SEG_HOST_PORT must be a valid port between 1 and 65535. Current value: ${SEG_HOST_PORT}"
	fi

	if ! is_port "${SEG_PORT}"; then
		die "SEG_PORT must be a valid port between 1 and 65535. Current value: ${SEG_PORT}"
	fi

	if [[ "${SEG_ROOT_DIR}" != /* ]]; then
		die "SEG_ROOT_DIR must be an absolute container path. Current value: ${SEG_ROOT_DIR}"
	fi
}

# Validate an existing token only; this startup script must never generate tokens.
validate_existing_token_file() {
	local token

	token="$(read_token)" || {
		error "Run ./scripts/seg-configure.sh to create a valid SEG API token."
		return 1
	}

	if ! validate_token_strength "${token}"; then
		error "Existing SEG API token is too weak. Run ./scripts/seg-configure.sh or replace it manually with a strong token."
		return 1
	fi

	return 0
}

# Keep host user as owner, grant SEG container group read access, and use mode 0640.
set_secret_file_permissions() {
	local host_uid
	local expected_group
	local secret_path_display

	host_uid="$(id -u)"
	expected_group="${SEG_CONTAINER_GID:-}"
	secret_path_display="$(path_relative_to_pwd "${SEG_SECRET_FILE}")"

	if ! is_non_empty "${expected_group}"; then
		error "Missing required runtime variable: SEG_CONTAINER_GID"
		return 1
	fi

	if [[ "${DRY_RUN:-false}" == "true" ]]; then
		run chown "${host_uid}:${expected_group}" "${secret_path_display}"
		run chmod 640 "${secret_path_display}"
		return 0
	fi

	if ! chown "${host_uid}:${expected_group}" "${SEG_SECRET_FILE}" 2>/dev/null; then
		error "Failed to set SEG API token ownership to ${host_uid}:${expected_group}."
		error "Manually run: sudo chown ${host_uid}:${expected_group} ${secret_path_display}"
		return 1
	fi

	if ! chmod 640 "${SEG_SECRET_FILE}" 2>/dev/null; then
		error "Failed to set SEG API token permissions to 640."
		error "Manually run: sudo chmod 640 ${secret_path_display}"
		return 1
	fi

	return 0
}

# Warn when user-specs is missing; seg-configure.sh is responsible for creating it.
check_user_specs_dir() {
	if [[ -d "${SEG_USER_SPECS_DIR}" ]]; then
		return 0
	fi

	warn "User specs directory not found: $(path_relative_to_pwd "${SEG_USER_SPECS_DIR}")"
	warn "Custom user modules will not be available. Run ./scripts/seg-configure.sh or create user-specs/ manually."
}

# Ensure the external Docker network exists before compose startup.
ensure_docker_network() {
	if docker network inspect "${SEG_SHARED_NETWORK}" >/dev/null 2>&1; then
		say_success "Docker network exists: ${SEG_SHARED_NETWORK}"
		return 0
	fi

	say_info "Creating Docker network: ${SEG_SHARED_NETWORK}"

	if [[ "${DRY_RUN:-false}" == "true" ]]; then
		run docker network create "${SEG_SHARED_NETWORK}"
	else
		run docker network create "${SEG_SHARED_NETWORK}" >/dev/null
	fi

	say_success "Docker network ready: ${SEG_SHARED_NETWORK}"
}

# Wait for the health endpoint and show diagnostics on timeout (except silent mode).
wait_for_health() {
	local timeout_seconds="60"
	local interval_seconds="2"
	local elapsed="0"
	local url

	url="$(health_url)"
	say_info "Waiting for SEG health endpoint: ${url}"

	while (( elapsed < timeout_seconds )); do
		if curl -fsS "${url}" >/dev/null 2>&1; then
			say_success "SEG health endpoint is ready."
			return 0
		fi

		sleep "${interval_seconds}"
		elapsed=$((elapsed + interval_seconds))
	done

	error "SEG did not become healthy within ${timeout_seconds} seconds."

	if [[ "${SILENT_MODE}" != "true" ]]; then
		printf '\nContainer status:\n' >&2
		compose ps >&2 || true

		printf '\nRecent seg-core logs:\n' >&2
		compose logs --tail=80 seg-core >&2 || true
	fi

	return 1
}

# Print a runtime summary after successful startup.
print_final_output() {
	local docs_state="disabled by SEG_ENABLE_DOCS=false"

	[[ "${SILENT_MODE}" == "true" ]] && return 0

	if [[ "${SEG_ENABLE_DOCS:-false}" == "true" ]]; then
		docs_state="$(docs_url)"
	fi

	section "SEG Runtime Started"
	success "SEG runtime stack is running."

	printf '\nRuntime:\n'
	printf '  %-27s %s\n' "Base URL:" "$(base_url)"
	printf '  %-27s %s\n' "Health:" "$(health_url)"
	printf '  %-27s %s\n' "Swagger / OpenAPI docs:" "${docs_state}"
	printf '  %-27s %s\n' "Compose project:" "${COMPOSE_PROJECT_NAME:-seg}"
	printf '  %-27s %s\n' "Docker network:" "${SEG_SHARED_NETWORK}"
	printf '  %-27s %s\n' "Data volume:" "${SEG_DATA_VOLUME}"

	printf '\nFiles and directories:\n'
	printf '  %-27s %s\n' ".env" "ready"
	printf '  %-27s %s\n' "SEG API token file" "secrets/seg_api_token.txt"
	printf '  %-27s %s\n' "User specs directory" "user-specs/"
	printf '  %-27s %s\n' "Custom YAML modules" "place .yml/.yaml files in user-specs/"

	printf '\nAPI surface:\n'
	printf '  %-27s %s\n' "Files API" "/v1/files"
	printf '  %-27s %s\n' "Actions API" "/v1/actions"
}

# Print dry-run completion output without claiming runtime startup.
print_dry_run_output() {
	[[ "${SILENT_MODE}" == "true" ]] && return 0

	section "SEG Runtime Dry Run"
	success "Dry-run completed. No Docker resources were started or changed."
}

# Main startup flow: validate prerequisites, start stack, then optionally wait.
main() {
	parse_args "$@"
	validate_cli_flags

	say_section "SEG Runtime Startup"

	require_docker
	require_docker_compose

	if [[ "${WAIT_MODE}" == "true" ]]; then
		require_curl
	fi

	ensure_file_exists "${SEG_ENV_FILE}" ".env file" || {
		error "Run ./scripts/seg-configure.sh first."
		exit 1
	}

	ensure_file_exists "${SEG_COMPOSE_FILE}" "docker-compose.yml" || exit 1

	load_env required
	validate_runtime_env

	validate_existing_token_file || exit 1
	# Adjust file-based secret permissions right before compose startup.
	set_secret_file_permissions || exit 1
	check_user_specs_dir
	ensure_docker_network

	if [[ "${PULL_MODE}" == "true" ]]; then
		say_step "Pull SEG runtime image"
		compose_quiet_if_silent pull seg-core
	fi

	say_step "Start SEG runtime stack"
	compose_quiet_if_silent up -d

	if [[ "${WAIT_MODE}" == "true" ]]; then
		if [[ "${DRY_RUN:-false}" == "true" ]]; then
			say_info "Skipping health wait in dry-run mode."
		else
			wait_for_health
		fi
	fi

	if [[ "${DRY_RUN:-false}" == "true" ]]; then
		print_dry_run_output
	else
		print_final_output
	fi
}

main "$@"
