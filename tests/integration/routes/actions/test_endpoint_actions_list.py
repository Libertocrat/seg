"""Integration tests for the /v1/actions discovery endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def actions_client(client, valid_registry):
    """Return client with deterministic action registry injected."""

    client.app.state.action_registry = valid_registry
    return client


def _get_actions(actions_client, auth_headers, **params):
    """Call GET /v1/actions with authenticated headers."""

    return actions_client.get("/v1/actions", headers=auth_headers, params=params)


def test_list_actions_returns_modules(actions_client, auth_headers):
    """
    GIVEN a valid registry loaded in application state
    WHEN GET /v1/actions is requested
    THEN the response returns modules inside the success envelope
    """

    response = _get_actions(actions_client, auth_headers)

    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["error"] is None

    data = body["data"]
    assert "modules" in data
    assert isinstance(data["modules"], list)
    assert len(data["modules"]) > 0
    assert all(
        "tags" in action for module in data["modules"] for action in module["actions"]
    )


def test_list_actions_filter_by_tag(actions_client, auth_headers):
    """
    GIVEN actions with effective tags
    WHEN GET /v1/actions is requested with tag=validation
    THEN only actions containing that tag are returned
    """

    response = _get_actions(actions_client, auth_headers, tag="validation")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        for action in module["actions"]:
            assert "validation" in [tag.lower() for tag in action["tags"]]


def test_list_actions_filter_by_query(actions_client, auth_headers):
    """
    GIVEN actions with effective tags
    WHEN GET /v1/actions is requested with q=numeric
    THEN returned actions match action name, summary, description, or tags
    """

    response = _get_actions(actions_client, auth_headers, q="numeric")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        for action in module["actions"]:
            assert (
                "numeric" in action["action"].lower()
                or (action["summary"] and "numeric" in action["summary"].lower())
                or (
                    action["description"] and "numeric" in action["description"].lower()
                )
                or any("numeric" in tag.lower() for tag in action["tags"])
            )


def test_list_actions_filter_q_and_tag(actions_client, auth_headers):
    """
    GIVEN actions with mixed effective tags
    WHEN GET /v1/actions is requested with q=default and tag=optional-input
    THEN both filters are applied and remaining actions match both
    """

    response = _get_actions(
        actions_client,
        auth_headers,
        q="default",
        tag="optional-input",
    )

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        for action in module["actions"]:
            assert "optional-input" in [tag.lower() for tag in action["tags"]]
            assert (
                "default" in action["action"].lower()
                or (action["summary"] and "default" in action["summary"].lower())
                or (
                    action["description"] and "default" in action["description"].lower()
                )
                or any("default" in tag.lower() for tag in action["tags"])
            )


def test_list_actions_no_matches(actions_client, auth_headers):
    """
    GIVEN a query that does not match any action fields
    WHEN GET /v1/actions is requested with q=nonexistent
    THEN modules is returned as an empty list
    """

    response = _get_actions(actions_client, auth_headers, q="nonexistent")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]

    assert modules == []


def test_list_actions_invalid_param(actions_client, auth_headers):
    """
    GIVEN a query parameter containing a NUL byte
    WHEN GET /v1/actions is requested
    THEN the endpoint rejects the request with INVALID_PARAMS
    """

    response = _get_actions(actions_client, auth_headers, q="\x00")

    assert response.status_code == 400

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_PARAMS"
