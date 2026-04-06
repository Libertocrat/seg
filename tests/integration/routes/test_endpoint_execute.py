"""
Integration tests for the /v1/execute endpoint.

These tests validate the HTTP contract and wiring of the execute route.
They ensure that requests are validated, delegated to the dispatcher,
and that responses follow the ResponseEnvelope contract.

They do NOT test dispatcher internals or action business logic.
"""

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
