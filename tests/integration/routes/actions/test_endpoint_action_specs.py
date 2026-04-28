"""Integration tests for the /v1/actions/{action_id} endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def action_specs_client(client, valid_registry):
    """Return a test client with deterministic valid registry attached."""

    client.app.state.action_registry = valid_registry
    return client


def test_get_action_specs_success(action_specs_client, auth_headers):
    """
    GIVEN a valid action_id
    WHEN GET /v1/actions/{action_id}
    THEN the endpoint returns the full public spec
    """

    response = action_specs_client.get(
        "/v1/actions/test_runtime.ping",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["error"] is None

    data = body["data"]
    assert data["action_id"] == "test_runtime.ping"
    assert data["action"] == "ping"
    assert "params_schema" in data
    assert "response_schema" in data


def test_get_action_specs_not_found(action_specs_client, auth_headers):
    """
    GIVEN a non-existent action_id
    WHEN GET /v1/actions/{action_id}
    THEN the endpoint returns ACTION_NOT_FOUND
    """

    response = action_specs_client.get(
        "/v1/actions/invalid.action",
        headers=auth_headers,
    )

    assert response.status_code == 404

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ACTION_NOT_FOUND"


def test_get_action_specs_contains_required_fields(action_specs_client, auth_headers):
    """
    GIVEN a valid action
    WHEN retrieving its spec
    THEN all required public fields are present
    """

    response = action_specs_client.get(
        "/v1/actions/test_runtime.ping",
        headers=auth_headers,
    )

    data = response.json()["data"]

    assert "args" in data
    assert "flags" in data
    assert "outputs" in data
    assert isinstance(data["params_schema"], dict)
    assert isinstance(data["response_schema"], dict)


def test_get_action_specs_envelope(action_specs_client, auth_headers):
    """
    GIVEN a valid request
    WHEN response is returned
    THEN it follows ResponseEnvelope contract
    """

    response = action_specs_client.get(
        "/v1/actions/test_runtime.ping",
        headers=auth_headers,
    )

    body = response.json()
    assert set(body.keys()) == {"success", "data", "error"}
