"""Integration tests for the /v1/actions discovery endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def discovery_registry(tmp_path: Path, monkeypatch, settings):
    """Build a deterministic registry with tag/query-friendly action metadata."""

    import seg.actions.registry as registry_module

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    (specs_dir / "crypto_tools.yml").write_text(
        """
version: 1

module: crypto_tools
description: "Cryptography helpers"
authors:
  - "SEG Test Suite"
tags: "crypto, security"

binaries:
  - echo

actions:

  encrypt_text:
    description: "Encrypt text payload"
    summary: "Encrypt text"

    command:
      - binary: echo
      - "encrypt"

  decrypt_text:
    description: "Decrypt text payload"
    summary: "Decrypt text"

    command:
      - binary: echo
      - "decrypt"
""".strip(),
        encoding="utf-8",
    )

    (specs_dir / "utility_tools.yml").write_text(
        """
version: 1

module: utility_tools
description: "General utility actions"
authors:
  - "SEG Test Suite"
tags: "utility"

binaries:
  - echo

actions:

  ping:
    description: "Return ping output"
    summary: "Ping"

    command:
      - binary: echo
      - "pong"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(registry_module, "SPEC_DIRS", (specs_dir,))

    return registry_module.build_registry_from_specs(settings)


@pytest.fixture
def actions_client(client, discovery_registry):
    """Return client with deterministic action registry injected."""

    client.app.state.action_registry = discovery_registry
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


def test_list_actions_filter_by_tag(actions_client, auth_headers):
    """
    GIVEN modules with different tags
    WHEN GET /v1/actions is requested with tag=crypto
    THEN only modules containing the crypto tag are returned
    """

    response = _get_actions(actions_client, auth_headers, tag="crypto")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        assert "crypto" in [tag.lower() for tag in module["tags"]]


def test_list_actions_filter_by_query(actions_client, auth_headers):
    """
    GIVEN modules with actions that include encrypt and non-encrypt variants
    WHEN GET /v1/actions is requested with q=encrypt
    THEN returned actions match action name, summary, or description by query
    """

    response = _get_actions(actions_client, auth_headers, q="encrypt")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        for action in module["actions"]:
            assert (
                "encrypt" in action["action"].lower()
                or (action["summary"] and "encrypt" in action["summary"].lower())
                or (
                    action["description"] and "encrypt" in action["description"].lower()
                )
            )


def test_list_actions_filter_q_and_tag(actions_client, auth_headers):
    """
    GIVEN modules with mixed tags and action names
    WHEN GET /v1/actions is requested with q=encrypt and tag=crypto
    THEN both filters are applied and remaining actions match encrypt query
    """

    response = _get_actions(actions_client, auth_headers, q="encrypt", tag="crypto")

    assert response.status_code == 200

    modules = response.json()["data"]["modules"]
    assert modules

    for module in modules:
        assert "crypto" in [tag.lower() for tag in module["tags"]]

        for action in module["actions"]:
            assert "encrypt" in action["action"].lower()


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
