# tests/test_app_smoke.py
"""
Smoke tests for the SEG FastAPI application.

These tests ensure that the application can be instantiated,
routes are registered, and the service responds to basic health checks.
They do NOT test business logic or security invariants.
"""

from fastapi.testclient import TestClient

from seg.app import create_app
from seg.core.config import Settings

# ============================================================================
# Application startup
# ============================================================================


def test_app_starts_successfully(api_token):
    """
    GIVEN a valid Settings object
    WHEN the FastAPI app is created
    THEN the application instance is created without errors
    """
    settings = Settings.model_validate(
        {
            "seg_api_token": api_token,
            "seg_sandbox_dir": "/data",
            "seg_allowed_subdirs": "tmp",
        }
    )

    app = create_app(settings)

    assert app is not None
    assert app.title == "Secure Execution Gateway (SEG)"


# ============================================================================
# Health endpoint
# ============================================================================


def test_health_endpoint_returns_200():
    """
    GIVEN a running SEG application
    WHEN the /health endpoint is requested
    THEN it returns HTTP 200 with expected payload
    """
    settings = Settings.model_validate(
        {
            "seg_api_token": "test-token",
            "seg_sandbox_dir": "/data",
            "seg_allowed_subdirs": "tmp",
        }
    )

    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert body["data"]["status"] == "ok"
