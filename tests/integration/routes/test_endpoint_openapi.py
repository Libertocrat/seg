"""Integration tests for the generated OpenAPI contract.

These tests validate the runtime OpenAPI projection exposed by SEG.
They ensure security exposure, contract overrides, schema registration,
and error examples are documented as expected.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from seg.app import create_app

# ============================================================================
# Helpers
# ============================================================================


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


# ============================================================================
# Section: OpenAPI spec validation
# ============================================================================


def test_openapi_is_valid_spec(minimal_safe_env, monkeypatch):
    """Validate generated OpenAPI document against the spec.

    GIVEN docs are enabled
    WHEN `/openapi.json` is generated
    THEN the payload is a valid OpenAPI schema.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    monkeypatch.setenv("SEG_ENABLE_DOCS", "true")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    validate(schema)


# ============================================================================
# Section: Security contract
# ============================================================================


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


# ============================================================================
# Section: Execute contract projection
# ============================================================================


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


# ============================================================================
# Section: Global metadata
# ============================================================================


def test_openapi_includes_global_metadata_from_app_settings(
    minimal_safe_env,
    monkeypatch,
):
    """Validate global OpenAPI metadata projected from app initialization.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN title/version/description come from app configuration
    AND contact/license/externalDocs are exposed as configured.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    info = schema["info"]
    assert info["title"] == "Secure Execution Gateway (SEG)"
    assert info["version"] == "0.1.0"
    assert "Runtime-aware OpenAPI contract generation" in info["description"]

    assert info["contact"]["name"] == "Libertocrat"
    assert (
        info["contact"]["url"]
        == "https://github.com/Libertocrat/secure-execution-gateway"
    )
    assert info["contact"]["email"] == "libertocrat@proton.me"

    assert info["license"]["name"] == "Apache License 2.0"
    assert info["license"]["url"] == "https://www.apache.org/licenses/LICENSE-2.0.html"

    assert (
        schema["externalDocs"]["url"]
        == "https://github.com/Libertocrat/secure-execution-gateway"
    )


# ============================================================================
# Section: Public endpoint overrides
# ============================================================================


def test_openapi_applies_public_endpoint_response_overrides(
    minimal_safe_env,
    monkeypatch,
):
    """Validate explicit response-contract overrides for public endpoints.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN `/metrics` advertises `text/plain` metrics payload
    AND `/health` advertises canonical envelope example.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    metrics_get = schema["paths"]["/metrics"]["get"]
    metrics_200 = metrics_get["responses"]["200"]
    assert metrics_200["description"] == "Prometheus metrics snapshot"
    assert "text/plain" in metrics_200["content"]
    assert metrics_200["content"]["text/plain"]["schema"]["type"] == "string"

    health_get = schema["paths"]["/health"]["get"]
    health_200 = health_get["responses"]["200"]
    assert health_200["description"] == "Health success response"
    health_example = health_200["content"]["application/json"]["schema"]["example"]
    assert health_example["success"] is True
    assert health_example["error"] is None
    assert health_example["data"]["status"] == "ok"


# ============================================================================
# Section: Component schemas
# ============================================================================


def test_openapi_registers_action_models_and_prunes_internal_schemas(
    minimal_safe_env,
    monkeypatch,
):
    """Validate component schema registration/pruning for runtime OpenAPI.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN action-related models are registered in components
    AND internal FastAPI/Pydantic helper schemas are pruned.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    components = schema["components"]["schemas"]
    for model_name in (
        "ExecuteRequest",
        "ChecksumParams",
        "ChecksumResult",
        "DeleteParams",
        "DeleteResult",
        "FileMoveParams",
        "FileMoveResult",
        "MimeDetectParams",
        "MimeDetectResult",
        "FileVerifyParams",
        "FileVerifyResult",
    ):
        assert model_name in components

    assert "HTTPValidationError" not in components
    assert "ValidationError" not in components
    assert "HealthResult" not in components
    assert "ResponseEnvelope_HealthResult_" not in components


# ============================================================================
# Section: Error examples
# ============================================================================


def test_openapi_error_contract_replaces_default_422_with_public_error_examples(
    minimal_safe_env,
    monkeypatch,
):
    """Validate dynamic error response generation for `/v1/execute`.

    GIVEN docs are enabled
    WHEN generating the OpenAPI schema
    THEN FastAPI's generic 422 is replaced
    AND centralized public error examples are published.

    Args:
        minimal_safe_env: Fixture that provides required SEG environment vars.
        monkeypatch: Pytest helper used to set test-only environment values.
    """
    schema = _openapi_document(minimal_safe_env, monkeypatch)

    post = schema["paths"]["/v1/execute"]["post"]
    responses = post["responses"]

    assert "422" in responses
    examples_422 = responses["422"]["content"]["application/json"]["examples"]
    assert "UNPROCESSABLE_ENTITY" in examples_422

    # The generic FastAPI validation wrapper should not leak through examples.
    assert "ValidationError" not in str(examples_422)
