"""Integration tests for generated OpenAPI contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from seg.app import create_app


def _openapi_document(minimal_safe_env, monkeypatch) -> dict:
    """Fetch the generated OpenAPI document with docs enabled.

    GIVEN a valid minimal SEG runtime environment
    WHEN docs are explicitly enabled for the test app
    THEN `/openapi.json` returns a successful OpenAPI payload.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.

    Returns:
        Parsed OpenAPI JSON document.
    """

    monkeypatch.setenv("SEG_ENABLE_DOCS", "true")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_sets_security_for_private_and_public_routes(
    minimal_safe_env,
    monkeypatch,
):
    """Validate auth exposure for public vs private endpoints.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN global BearerAuth is enabled
    AND health/metrics are explicitly public.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    assert schema["security"] == [{"BearerAuth": []}]

    health_get = schema["paths"]["/health"]["get"]
    metrics_get = schema["paths"]["/metrics"]["get"]
    assert health_get["security"] == []
    assert metrics_get["security"] == []


def test_openapi_execute_contract_includes_integrity_and_request_id_headers(
    minimal_safe_env,
    monkeypatch,
):
    """Validate `/v1/execute` runtime contract projection in OpenAPI.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN `/v1/execute` includes dynamic request/data variants and integrity metadata
    AND `X-Request-Id` is documented as UUID on responses.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    post = schema["paths"]["/v1/execute"]["post"]

    integrity = post["x-seg-integrity"]
    assert integrity["content_type_required"] == "application/json"
    assert integrity["enforced_by"] == "RequestIntegrityMiddleware"
    assert isinstance(integrity["body_limit_bytes"], int)

    request_schema = post["requestBody"]["content"]["application/json"]["schema"]
    assert "oneOf" in request_schema
    assert len(request_schema["oneOf"]) >= 1

    for code in ("200", "400", "401", "429", "500", "504"):
        if code not in post["responses"]:
            continue
        headers = post["responses"][code].get("headers", {})
        assert "X-Request-Id" in headers
        header_schema = headers["X-Request-Id"]["schema"]
        assert header_schema["type"] == "string"
        assert header_schema["format"] == "uuid"

    retry_after_schema = post["responses"]["429"]["headers"]["Retry-After"]["schema"]
    assert retry_after_schema["type"] == "string"
    assert retry_after_schema["pattern"] == "^[0-9]+$"
