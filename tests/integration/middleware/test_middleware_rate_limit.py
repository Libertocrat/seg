"""
Integration tests for the RateLimitMiddleware.

These tests validate rate-limiting behavior as an HTTP-level contract.
They ensure that:

- Requests within budget proceed normally.
- Requests over budget are rejected with the expected envelope and headers.
- Retry-After values are reasonable for clients.
- Environment-based configuration is honored.
- Exempt endpoints bypass rate limiting.
- Metric labels use normalized paths.

They do NOT validate token-bucket internals.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from seg.app import create_app
from seg.core.config import Settings, get_settings
from seg.core.errors import RATE_LIMITED
from seg.middleware.rate_limit import RATE_LIMITED_TOTAL

# ==========================================================
# Helpers
# ==========================================================


def _rate_limited_metric_value(path: str, method: str, reason: str) -> float:
    """Return current seg_rate_limited_total value for a label set."""
    total = 0.0
    for metric in RATE_LIMITED_TOTAL.collect():
        for sample in metric.samples:
            if sample.name != "seg_rate_limited_total":
                continue
            labels = sample.labels
            if (
                labels.get("path") == path
                and labels.get("method") == method
                and labels.get("reason") == reason
            ):
                total += float(sample.value)
    return total


@pytest.fixture
def low_rps_settings(api_token, sandbox_dir, allowed_subdirs) -> Settings:
    """Return settings with a strict 1 RPS limit."""
    return Settings.model_validate(
        {
            "seg_api_token": api_token,
            "seg_sandbox_dir": str(sandbox_dir),
            "seg_allowed_subdirs": allowed_subdirs,
            "seg_rate_limit_rps": 1,
        }
    )


@pytest.fixture(scope="function")
def low_rps_app(low_rps_settings):
    """Create app configured with 1 RPS for deterministic rejection tests."""
    return create_app(low_rps_settings)


@pytest.fixture(scope="function")
def low_rps_client(low_rps_app):
    """Create HTTP client bound to low-RPS app."""
    with TestClient(low_rps_app) as client:
        yield client
    # Use context manager to ensure app shutdown; no further cleanup needed.


@pytest.fixture
def low_rps_docs_settings(api_token, sandbox_dir, allowed_subdirs) -> Settings:
    """Return settings with docs enabled and strict 1 RPS limit."""
    return Settings.model_validate(
        {
            "seg_api_token": api_token,
            "seg_sandbox_dir": str(sandbox_dir),
            "seg_allowed_subdirs": allowed_subdirs,
            "seg_rate_limit_rps": 1,
            "seg_enable_docs": True,
        }
    )


@pytest.fixture
def low_rps_docs_app(low_rps_docs_settings):
    """Create app configured with docs enabled and 1 RPS."""
    return create_app(low_rps_docs_settings)


@pytest.fixture
def low_rps_docs_client(low_rps_docs_app):
    """Create HTTP client bound to low-RPS docs-enabled app."""
    return TestClient(low_rps_docs_app)


# ==========================================================
# Section: Happy path
# ==========================================================


def test_request_within_limit_proceeds_without_429(client, auth_headers):
    """
    GIVEN the default configured rate limit
    WHEN a request is made within the available budget
    THEN it proceeds normally and is not rejected with 429
    """
    response = client.post(
        "/v1/execute", json={"action": "noop", "params": {}}, headers=auth_headers
    )

    assert response.status_code != RATE_LIMITED.http_status
    body = response.json()
    assert isinstance(body, dict)
    assert "success" in body
    assert "error" in body


# ==========================================================
# Section: Rate limit exceeded
# ==========================================================


def test_rate_limit_exceeded_returns_429_envelope_headers_and_metric(
    low_rps_client, auth_headers
):
    """
    GIVEN a strict rate limit of 1 request per second
    WHEN two requests are made immediately
    THEN the second request is rejected with 429 and proper contract metadata
    """
    reason = "token_bucket_exhausted"
    before = _rate_limited_metric_value("/v1/execute", "POST", reason)

    first = low_rps_client.post("/v1/execute", json={}, headers=auth_headers)
    second = low_rps_client.post("/v1/execute", json={}, headers=auth_headers)

    assert first.status_code != RATE_LIMITED.http_status
    assert second.status_code == RATE_LIMITED.http_status

    body = second.json()
    assert body.get("success") is False
    assert body.get("error") is not None
    assert body["error"].get("code") == RATE_LIMITED.code
    assert "X-Request-Id" in second.headers
    assert "Retry-After" in second.headers
    assert int(second.headers["Retry-After"]) > 0

    after = _rate_limited_metric_value("/v1/execute", "POST", reason)
    assert after == before + 1.0


# ==========================================================
# Section: Retry-After correctness
# ==========================================================


def test_retry_after_is_integer_and_reasonable_for_one_rps(
    low_rps_client, auth_headers
):
    """
    GIVEN a strict rate limit of 1 request per second
    WHEN the second immediate request is rejected
    THEN Retry-After is an integer >= 1 and within a small timing tolerance
    """
    low_rps_client.post("/v1/execute", json={}, headers=auth_headers)
    rejected = low_rps_client.post("/v1/execute", json={}, headers=auth_headers)

    assert rejected.status_code == RATE_LIMITED.http_status

    retry_after = int(rejected.headers["Retry-After"])
    assert retry_after >= 1
    assert retry_after <= 2


# ==========================================================
# Section: Environment configuration
# ==========================================================


def test_rate_limit_respects_env_configuration(
    monkeypatch,
    tmp_path,
    api_token,
    auth_headers,
):
    """
    GIVEN SEG_RATE_LIMIT_RPS=2 configured via environment variables
    WHEN the app is created from environment-backed settings
    THEN the third immediate request is rate limited
    """
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    (sandbox_dir / "tmp").mkdir()

    monkeypatch.setenv("SEG_API_TOKEN", api_token)
    monkeypatch.setenv("SEG_SANDBOX_DIR", str(sandbox_dir))
    monkeypatch.setenv("SEG_ALLOWED_SUBDIRS", "tmp")
    monkeypatch.setenv("SEG_RATE_LIMIT_RPS", "2")

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    first = client.post("/v1/execute", json={}, headers=auth_headers)
    second = client.post("/v1/execute", json={}, headers=auth_headers)
    third = client.post("/v1/execute", json={}, headers=auth_headers)

    assert first.status_code != RATE_LIMITED.http_status
    assert second.status_code != RATE_LIMITED.http_status
    assert third.status_code == RATE_LIMITED.http_status


# ==========================================================
# Section: Exempt endpoints
# ==========================================================


def test_metrics_endpoint_is_exempt_even_when_bucket_is_exhausted(
    low_rps_client, auth_headers
):
    """
    GIVEN an exhausted rate-limit bucket
    WHEN the metrics endpoint is requested
    THEN /metrics remains accessible because it is exempt
    """
    low_rps_client.post("/v1/execute", json={}, headers=auth_headers)
    limited = low_rps_client.post("/v1/execute", json={}, headers=auth_headers)
    assert limited.status_code == RATE_LIMITED.http_status

    metrics = low_rps_client.get("/metrics")
    assert metrics.status_code == 200


def test_docs_endpoints_are_exempt_when_docs_are_enabled(
    low_rps_docs_client, auth_headers
):
    """
    GIVEN docs are enabled and the bucket is exhausted
    WHEN /docs is requested
    THEN docs remain accessible because docs endpoints are exempt
    """
    low_rps_docs_client.post("/v1/execute", json={}, headers=auth_headers)
    limited = low_rps_docs_client.post("/v1/execute", json={}, headers=auth_headers)
    assert limited.status_code == RATE_LIMITED.http_status

    docs = low_rps_docs_client.get("/docs")
    assert docs.status_code == 200


# ==========================================================
# Section: Metric path normalization
# ==========================================================


def test_metric_path_label_is_normalized_on_rejection(low_rps_client, auth_headers):
    """
    GIVEN a request path with trailing slash and query string
    WHEN rate limit rejection happens
    THEN metric labels use normalized path without trailing slash or query
    """
    reason = "token_bucket_exhausted"
    before_normalized = _rate_limited_metric_value("/v1/execute", "POST", reason)
    before_raw = _rate_limited_metric_value("/v1/execute/", "POST", reason)

    # Hit canonical path first to avoid redirects consuming the token.
    allowed = low_rps_client.post(
        "/v1/execute",
        json={},
        headers=auth_headers,
    )
    # Then call variant with query; it should be rejected
    # and labeled with normalized path.
    rejected = low_rps_client.post("/v1/execute/?a=1", json={}, headers=auth_headers)

    assert allowed.status_code != RATE_LIMITED.http_status
    assert rejected.status_code == RATE_LIMITED.http_status

    after_normalized = _rate_limited_metric_value("/v1/execute", "POST", reason)
    after_raw = _rate_limited_metric_value("/v1/execute/", "POST", reason)

    assert after_normalized == before_normalized + 1.0
    assert after_raw == before_raw
