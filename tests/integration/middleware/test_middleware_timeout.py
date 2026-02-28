"""
Integration tests for the TimeoutMiddleware.

These tests validate timeout enforcement as an HTTP-level contract.
They ensure that:

- Slow handlers are terminated with HTTP 504.
- The ResponseEnvelope failure contract is preserved.
- X-Request-Id propagates correctly.
- Metrics are incremented correctly.
- Exempt endpoints bypass timeout.
- SegActionError is NOT converted into timeout.
- Timeout takes priority over domain errors.

They do NOT validate internal asyncio mechanics.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from seg.app import create_app
from seg.core.config import Settings
from seg.core.errors import INVALID_REQUEST, TIMEOUT
from seg.core.schemas.envelope import ResponseEnvelope
from seg.middleware.timeout import TIMEOUTS_TOTAL

# ============================================================================
# Helpers
# ============================================================================


def _timeout_metric_value(path: str, method: str) -> float:
    """Return current `seg_timeouts_total` value for a label set.

    Args:
        path: Normalized request path label.
        method: Uppercase HTTP method label.

    Returns:
        Aggregated metric value for the provided labels.
    """
    total = 0.0
    for metric in TIMEOUTS_TOTAL.collect():
        for sample in metric.samples:
            if sample.name != "seg_timeouts_total":
                continue
            labels = sample.labels
            if labels.get("path") == path and labels.get("method") == method:
                total += float(sample.value)
    return total


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def low_timeout_settings(api_token, sandbox_dir, allowed_subdirs) -> Settings:
    """Return settings with a strict 100ms timeout.

    Args:
        api_token: Authentication token fixture.
        sandbox_dir: Sandbox root directory fixture.
        allowed_subdirs: CSV allowlist of sandbox subdirectories.

    Returns:
        Settings configured for low timeout tests.
    """
    return Settings.model_validate(
        {
            "seg_api_token": api_token,
            "seg_sandbox_dir": str(sandbox_dir),
            "seg_allowed_subdirs": allowed_subdirs,
            "seg_timeout_ms": 100,
        }
    )


@pytest.fixture
def low_timeout_app(low_timeout_settings):
    """Create app configured with 100ms timeout for deterministic tests.

    Args:
        low_timeout_settings: Settings fixture with low timeout.

    Returns:
        FastAPI application configured for timeout tests.
    """
    return create_app(low_timeout_settings)


@pytest.fixture
def low_timeout_client(low_timeout_app):
    """Create HTTP client bound to low-timeout app.

    Args:
        low_timeout_app: App fixture configured for timeout tests.

    Yields:
        TestClient bound to the configured app.
    """
    with TestClient(low_timeout_app) as client:
        yield client


# ============================================================================
# Fixtures: Slow endpoint handlers
# ============================================================================


@pytest.fixture
def slow_health_endpoint(monkeypatch):
    """Patch `/health` to simulate a slow response.

    Args:
        monkeypatch: Pytest helper for runtime attribute patching.

    Returns:
        None. The route handler is patched in-place.
    """

    async def slow_health():
        await asyncio.sleep(0.2)
        payload = ResponseEnvelope.success_response({"status": "ok"}).model_dump()
        return JSONResponse(payload)

    monkeypatch.setattr(
        "seg.routes.health.health",
        slow_health,
    )


@pytest.fixture
def slow_metrics_endpoint(monkeypatch):
    """Patch `/metrics` to simulate a slow response.

    Args:
        monkeypatch: Pytest helper for runtime attribute patching.

    Returns:
        None. The route handler is patched in-place.
    """

    async def slow_metrics():
        await asyncio.sleep(0.2)
        data = generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    monkeypatch.setattr("seg.routes.metrics.metrics", slow_metrics)


@pytest.fixture
def slow_execute_endpoint_success(monkeypatch):
    """Patch dispatcher to simulate slow successful execution.

    Args:
        monkeypatch: Pytest helper for runtime attribute patching.

    Returns:
        None. The dispatcher is patched in-place.
    """

    async def slow_dispatch(req):
        await asyncio.sleep(0.2)
        envelope = ResponseEnvelope.success_response({"result": "ok"})
        return envelope, 200

    monkeypatch.setattr(
        "seg.routes.execute.dispatch_execute",
        slow_dispatch,
    )


@pytest.fixture
def slow_execute_endpoint_error(monkeypatch):
    """Patch dispatcher to simulate slow execution returning domain failure.

    Args:
        monkeypatch: Pytest helper for runtime attribute patching.

    Returns:
        None. The dispatcher is patched in-place.
    """

    async def slow_dispatch(req):
        await asyncio.sleep(0.2)

        envelope = ResponseEnvelope.failure(
            code=INVALID_REQUEST.code,
            message="delayed boom",
        )

        return envelope, INVALID_REQUEST.http_status

    monkeypatch.setattr(
        "seg.routes.execute.dispatch_execute",
        slow_dispatch,
    )


# ============================================================================
# Section: Generic slow handler timeout
# ============================================================================


def test_generic_slow_handler_is_intercepted_by_timeout(
    low_timeout_app,
    low_timeout_client,
    auth_headers,
):
    """
    GIVEN a timeout of 100ms
    WHEN a handler sleeps longer than the timeout
    THEN HTTP 504 is returned with proper envelope and metric increment
    """

    @low_timeout_app.get("/test-slow")
    async def slow_handler():
        await asyncio.sleep(0.5)
        return {"ok": True}

    before = _timeout_metric_value("/test-slow", "GET")

    response = low_timeout_client.get("/test-slow", headers=auth_headers)

    assert response.status_code == TIMEOUT.http_status
    body = response.json()
    assert body["success"] is False
    assert body["error"] is not None
    assert body["error"]["code"] == TIMEOUT.code
    assert "X-Request-Id" in response.headers

    after = _timeout_metric_value("/test-slow", "GET")
    assert after == before + 1.0


# ============================================================================
# Section: Execute endpoint behavior
# ============================================================================


def test_seg_action_error_is_not_converted_to_timeout(
    low_timeout_client,
    auth_headers,
):
    """
    GIVEN a handler that raises SegActionError immediately
    WHEN it executes
    THEN it is NOT converted into a timeout response
    """
    response = low_timeout_client.post(
        "/v1/execute",
        json={"action": "raise_seg_action_error", "params": {}},
        headers=auth_headers,
    )

    assert response.status_code != TIMEOUT.http_status
    body = response.json()
    assert body["success"] is False
    assert body["error"] is not None
    assert body["data"] is None
    assert body["error"]["code"] != TIMEOUT.code


def test_slow_execute_success_is_intercepted_by_timeout(
    low_timeout_client,
    slow_execute_endpoint_success,
    auth_headers,
    sandbox_file_factory,
):
    """
    GIVEN a slow successful action (> timeout)
    WHEN it executes
    THEN TIMEOUT takes priority
    """

    # Create valid file for checksum action
    sf = sandbox_file_factory(
        name="file.txt",
        content=b"hello",
    )

    payload = {
        "action": "file_checksum",
        "params": {
            "path": str(sf.rel_path),
        },
    }

    before = _timeout_metric_value("/v1/execute", "POST")

    response = low_timeout_client.post(
        "/v1/execute",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == TIMEOUT.http_status

    body = response.json()
    assert body["success"] is False
    assert body["error"] is not None
    assert body["error"]["code"] == TIMEOUT.code

    after = _timeout_metric_value("/v1/execute", "POST")
    assert after == before + 1.0


def test_slow_execute_error_is_intercepted_by_timeout(
    low_timeout_client,
    slow_execute_endpoint_error,
    auth_headers,
    sandbox_file_factory,
):
    """
    GIVEN a slow action that eventually raises SegActionError
    WHEN it exceeds timeout
    THEN TIMEOUT is returned instead of domain error
    """

    # Create valid file for checksum action
    sf = sandbox_file_factory(
        name="file.txt",
        content=b"hello",
    )

    payload = {
        "action": "file_checksum",
        "params": {
            "path": str(sf.rel_path),
        },
    }

    before = _timeout_metric_value("/v1/execute", "POST")

    response = low_timeout_client.post(
        "/v1/execute",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == TIMEOUT.http_status

    body = response.json()
    assert body["success"] is False
    assert body["error"] is not None
    assert body["error"]["code"] == TIMEOUT.code
    assert body["error"]["code"] != INVALID_REQUEST.code

    after = _timeout_metric_value("/v1/execute", "POST")
    assert after == before + 1.0


# ============================================================================
# Section: Exempt endpoints
# ============================================================================


def test_health_endpoint_is_exempt_from_timeout(low_timeout_client):
    """
    GIVEN a low timeout configuration
    WHEN /health is requested
    THEN it returns 200 and is not timed out
    """

    response = low_timeout_client.get("/health")

    assert response.status_code == 200


def test_metrics_endpoint_is_exempt_from_timeout(low_timeout_client):
    """
    GIVEN a low timeout configuration
    WHEN /metrics is requested
    THEN it returns 200 and is not timed out
    """

    response = low_timeout_client.get("/metrics")

    assert response.status_code == 200


def test_slow_health_is_not_intercepted_by_timeout(
    low_timeout_client,
    slow_health_endpoint,
):
    """
    GIVEN a slow /health handler (> timeout)
    WHEN it executes
    THEN it is NOT intercepted
    """

    before = _timeout_metric_value("/health", "GET")

    response = low_timeout_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    after = _timeout_metric_value("/health", "GET")
    assert after == before


def test_slow_metrics_is_not_intercepted_by_timeout(
    low_timeout_client,
    slow_metrics_endpoint,
):
    """
    GIVEN a slow /metrics handler (> timeout)
    WHEN it executes
    THEN it is NOT intercepted
    """

    before = _timeout_metric_value("/metrics", "GET")

    response = low_timeout_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers.get("content-type") == CONTENT_TYPE_LATEST

    after = _timeout_metric_value("/metrics", "GET")
    assert after == before


# ============================================================================
# Section: Metrics path normalization
# ============================================================================


def test_timeout_metric_uses_normalized_path(
    low_timeout_app,
    low_timeout_client,
    auth_headers,
):
    """
    GIVEN a slow handler registered at /test-slow-normalized
    WHEN it is called with trailing slash and query string
    THEN metric label uses normalized path
    """

    @low_timeout_app.get("/test-slow-normalized")
    async def slow():
        await asyncio.sleep(0.5)
        return {"ok": True}

    before_normalized = _timeout_metric_value("/test-slow-normalized", "GET")
    before_raw = _timeout_metric_value("/test-slow-normalized/", "GET")

    response = low_timeout_client.get(
        "/test-slow-normalized/?a=1", headers=auth_headers
    )

    after_normalized = _timeout_metric_value("/test-slow-normalized", "GET")
    after_raw = _timeout_metric_value("/test-slow-normalized/", "GET")

    assert response.status_code == TIMEOUT.http_status
    payload = response.json()
    assert payload["error"]["code"] == TIMEOUT.code
    assert after_normalized == before_normalized + 1.0
    assert after_raw == before_raw
