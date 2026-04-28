"""
Integration tests for the /v1/execute endpoint.

These tests validate the HTTP contract and wiring of the execute route.
They ensure that requests are validated, delegated to the dispatcher,
and that responses follow the ResponseEnvelope contract.

They do NOT test dispatcher internals or action business logic.
"""

from pathlib import Path

import pytest

from seg.actions.exceptions import (
    ActionBinaryBlockedError,
    ActionBinaryNotAllowedError,
    ActionBinaryPathForbiddenError,
)

# ============================================================================
# Request Validation
# ============================================================================


def test_execute_rejects_invalid_payload(client, auth_headers):
    """
    GIVEN an invalid execute request payload
    WHEN the /v1/execute endpoint is called
    THEN it returns HTTP 422 due to request validation failure
    """
    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={},  # missing required fields
    )

    assert response.status_code == 422


# ============================================================================
# Success Cases
# ============================================================================


def test_execute_returns_success_envelope_for_valid_action(
    client, auth_headers, valid_registry
):
    """
    GIVEN a valid execute request for a registered action
    WHEN the /v1/execute endpoint is called
    THEN it returns HTTP 200 with a success ResponseEnvelope
    """

    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.repeat",
        "params": {"count": 5},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, dict)
    assert body["success"] is True
    assert body["data"]["stdout"].strip() == "5"
    assert body["error"] is None
    assert body["data"]["exit_code"] == 0
    assert "stdout" in body["data"]
    assert "stdout_encoding" in body["data"]


def test_execute_uses_default_param_value(client, auth_headers, valid_registry):
    """
    GIVEN an action with a default parameter value
    WHEN no parameter is provided
    THEN the default value is used in execution
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.default_test",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert "5" in body["data"]["stdout"]


# ============================================================================
# Domain Errors
# ============================================================================


def test_execute_returns_error_envelope_for_unknown_action(
    client,
    auth_headers,
):
    """
    GIVEN an execute request for an unknown action
    WHEN the /v1/execute endpoint is called
    THEN it returns a stable error ResponseEnvelope
    """
    payload = {
        "action": "non_existent_action",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    from seg.core.errors import ACTION_NOT_FOUND

    assert response.status_code == ACTION_NOT_FOUND.http_status

    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] is not None
    assert body["error"]["code"] == ACTION_NOT_FOUND.code
    assert "message" in body["error"]


def test_execute_invalid_param_type_maps_to_invalid_params(
    client, auth_headers, valid_registry
):
    """
    GIVEN an action expecting an integer parameter
    WHEN a non-integer value is provided
    THEN the endpoint returns INVALID_PARAMS error
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.repeat",
        "params": {"count": "not-an-int"},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert response.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_PARAMS"
    assert "errors" in body["error"]["details"]


def test_execute_missing_required_param_maps_to_invalid_params(
    client, auth_headers, valid_registry
):
    """
    GIVEN an action with a required parameter
    WHEN the parameter is omitted
    THEN the endpoint returns INVALID_PARAMS error
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.repeat",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == "INVALID_PARAMS"


def test_execute_renderer_error_maps_to_invalid_params(
    client, auth_headers, valid_registry
):
    """
    GIVEN an action receiving a None value
    WHEN the renderer processes the parameters
    THEN the endpoint returns INVALID_PARAMS error
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.repeat",
        "params": {"count": None},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == "INVALID_PARAMS"


def test_execute_out_of_range_param_maps_to_invalid_params(
    client, auth_headers, valid_registry
):
    """
    GIVEN an action with numeric constraints
    WHEN the value is outside the allowed range
    THEN the endpoint returns INVALID_PARAMS error
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.range_test",
        "params": {"value": 999},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == "INVALID_PARAMS"


@pytest.mark.parametrize(
    ("raised_error", "test_id"),
    [
        (ActionBinaryBlockedError("blocked"), "blocked_binary"),
        (ActionBinaryNotAllowedError("not_allowed"), "not_allowed_binary"),
        (ActionBinaryPathForbiddenError("path_forbidden"), "path_like_binary"),
    ],
    ids=["blocked_binary", "not_allowed_binary", "path_like_binary"],
)
def test_execute_binary_policy_errors_map_to_permission_denied(
    client,
    auth_headers,
    monkeypatch,
    raised_error,
    test_id,
):
    """
    GIVEN dispatcher raises a binary-policy runtime error
    WHEN /v1/execute is called
    THEN endpoint maps error to PERMISSION_DENIED envelope
    """
    _ = test_id

    async def _raise(*_args, **_kwargs):
        """Raise the parametrized dispatcher error for mapping tests."""
        raise raised_error

    monkeypatch.setattr(
        "seg.routes.actions.handlers.execute_action.dispatch_action",
        _raise,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "test_runtime.ping", "params": {}},
    )

    body = response.json()

    assert response.status_code == 403
    assert body["success"] is False
    assert body["error"]["code"] == "PERMISSION_DENIED"


# ============================================================================
# Response Contract
# ============================================================================


def test_execute_output_encoding_fields_present(client, auth_headers, valid_registry):
    """
    GIVEN a successful execution
    WHEN the response is returned
    THEN encoding metadata is included in the output
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.ping",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert body["data"]["stdout_encoding"] in ("utf-8", "base64")
    assert body["data"]["stderr_encoding"] in ("utf-8", "base64")


def test_execute_stderr_fields_always_present(client, auth_headers, valid_registry):
    """
    GIVEN a successful execution
    WHEN the response is returned
    THEN stderr fields are always present
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.ping",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert "stderr" in body["data"]
    assert "stderr_encoding" in body["data"]


def test_execute_response_envelope_contract(client, auth_headers, valid_registry):
    """
    GIVEN a valid execution request
    WHEN the response is returned
    THEN it follows the ResponseEnvelope contract
    """
    client.app.state.action_registry = valid_registry

    payload = {
        "action": "test_runtime.ping",
        "params": {},
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    body = response.json()

    assert set(body.keys()) == {"success", "data", "error"}


def _build_outputs_registry(
    *,
    specs_root: Path,
    monkeypatch,
    settings,
):
    """Build test registry containing actions with DSL outputs.

    Args:
        specs_root: Temporary directory where DSL specs are written.
        monkeypatch: Pytest monkeypatch fixture.
        settings: Application settings used for registry build.

    Returns:
        Compiled ActionRegistry with outputs-capable actions.
    """

    import seg.actions.registry as registry_module

    specs_dir = specs_root / "specs_outputs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    spec_file = specs_dir / "outputs_runtime.yml"
    spec_file.write_text(
        """
version: 1
module: outputs_runtime
description: "Outputs integration test module"

binaries:
    - echo
    - "false"

actions:
    copy_cmd_output:
        description: "Create command output placeholder path argument"
        outputs:
            cmd_out_file:
                type: file
                source: command
                description: "File produced by command output placeholder"
        command:
            - binary: echo
            - "CMD_OUTPUT"
            - output: cmd_out_file

    stdout_to_output:
        description: "Create stdout-derived file output"
        outputs:
            stdout_file:
                type: file
                source: stdout
                description: "File materialized from stdout bytes"
        command:
            - binary: echo
            - "HELLO_STDOUT"

    fail_cmd_output:
        description: "Fail command and cleanup output placeholders"
        outputs:
            cmd_out_file:
                type: file
                source: command
                description: "Command output placeholder cleaned on failure"
        command:
            - binary: "false"
            - output: cmd_out_file

    copy_with_stdout_output:
        description: "Emit command and stdout outputs together"
        outputs:
            cmd_out_file:
                type: file
                source: command
                description: "Primary command output file"
            stdout_file:
                type: file
                source: stdout
                description: "Secondary stdout-derived output file"
        command:
            - binary: echo
            - "MULTI_OUTPUT"
            - output: cmd_out_file
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(registry_module, "SPEC_DIRS", (specs_dir,))
    return registry_module.build_registry_from_specs(settings)


# ============================================================================
# Outputs Integration
# ============================================================================


def test_execute__returns_file_command_output(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN action with file+command output
    WHEN /v1/execute is called
    THEN response contains outputs metadata for command output
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.copy_cmd_output", "params": {}},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["outputs"] is not None
    assert body["data"]["outputs"]["cmd_out_file"] is not None
    assert "id" in body["data"]["outputs"]["cmd_out_file"]


def test_execute__file_command_output_is_ready(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN successful execution
    WHEN /v1/execute returns
    THEN command output file status is ready
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.copy_cmd_output", "params": {}},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["data"]["outputs"]["cmd_out_file"]["status"] == "ready"


def test_execute__returns_file_stdout_output(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN action with file+stdout output
    WHEN /v1/execute is called
    THEN response contains stdout-derived output metadata
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.stdout_to_output", "params": {}},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["data"]["outputs"] is not None
    assert body["data"]["outputs"]["stdout_file"] is not None


def test_execute__stdout_file_contains_stdout(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN stdout output action
    WHEN /v1/execute returns outputs
    THEN output blob content matches stdout bytes
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.stdout_to_output", "params": {}},
    )
    body = response.json()
    output_id = body["data"]["outputs"]["stdout_file"]["id"]

    content_response = client.get(
        f"/v1/files/{output_id}/content", headers=auth_headers
    )

    assert response.status_code == 200
    assert content_response.status_code == 200
    assert content_response.content == b"HELLO_STDOUT\n"


def test_execute__command_failure_returns_null_output(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN command failure action
    WHEN /v1/execute is called
    THEN command output is returned as null
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.fail_cmd_output", "params": {}},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["data"]["exit_code"] != 0
    assert body["data"]["outputs"]["cmd_out_file"] is None


def test_execute__command_failure_cleans_up_files(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN command failure action
    WHEN /v1/execute is called
    THEN no placeholder metadata files remain after cleanup
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    meta_dir = Path(settings.seg_root_dir) / "data" / "files" / "meta"
    before_count = len(list(meta_dir.glob("file_*.json"))) if meta_dir.exists() else 0

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.fail_cmd_output", "params": {}},
    )

    after_count = len(list(meta_dir.glob("file_*.json"))) if meta_dir.exists() else 0

    assert response.status_code == 200
    assert after_count == before_count


def test_execute__multiple_outputs_are_returned(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN action declaring command and stdout file outputs
    WHEN /v1/execute is called
    THEN both outputs are present in response payload
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.copy_with_stdout_output", "params": {}},
    )

    body = response.json()
    outputs = body["data"]["outputs"]

    assert response.status_code == 200
    assert outputs is not None
    assert "cmd_out_file" in outputs
    assert "stdout_file" in outputs


def test_execute__output_order_is_preserved(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
    settings,
):
    """
    GIVEN action with multiple declared outputs
    WHEN /v1/execute returns outputs
    THEN output key order matches DSL declaration order
    """

    client.app.state.action_registry = _build_outputs_registry(
        specs_root=tmp_path,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json={"action": "outputs_runtime.copy_with_stdout_output", "params": {}},
    )

    body = response.json()

    assert response.status_code == 200
    assert list(body["data"]["outputs"].keys()) == ["cmd_out_file", "stdout_file"]
