"""
Integration tests for the /v1/execute endpoint.

These tests validate the HTTP contract and wiring of the execute route.
They ensure that requests are validated, delegated to the dispatcher,
and that responses follow the ResponseEnvelope contract.

They do NOT test dispatcher internals or action business logic.
"""

# ============================================================================
# Execute endpoint – request validation
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
# Execute endpoint – happy path
# ============================================================================


def test_execute_returns_success_envelope_for_valid_action(
    client, auth_headers, sandbox_file_factory
):
    """
    GIVEN a valid execute request for a registered action
    WHEN the /v1/execute endpoint is called
    THEN it returns HTTP 200 with a success ResponseEnvelope
    """

    file = sandbox_file_factory(
        name="file.txt",
        content=b"hello world",
    )

    payload = {
        "action": "file_checksum",
        "params": {
            "path": str(file.rel_path),
        },
    }

    response = client.post(
        "/v1/execute",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, dict)
    assert body.get("success") is True
    assert body.get("data") is not None
    assert body.get("error") is None


# ============================================================================
# Execute endpoint – domain errors
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
    assert body.get("success") is False
    assert body.get("data") is None
    assert body.get("error") is not None
    assert body["error"].get("code") == ACTION_NOT_FOUND.code
    assert "message" in body["error"]
