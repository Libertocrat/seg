# tests/conftest.py
"""
Global pytest fixtures for SEG test suite.

This module defines shared fixtures used across unit, integration, and
smoke tests. The primary goals are:

- Ensure full isolation from the local environment (.env, shell variables).
- Provide minimal, valid defaults for Settings-dependent tests.
- Enable authenticated HTTP requests against the FastAPI app.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from seg.app import create_app
from seg.core.config import Settings

# ============================================================================
# Environment isolation
# ============================================================================


@pytest.fixture(autouse=True)
def clean_seg_environment(monkeypatch):
    """Ensure test-only isolation from local configuration sources.

    This fixture enforces *strict configuration isolation* for all tests by:

    - Removing any `SEG_*` variables from the process environment.
    - Disabling `.env` file loading in `Settings` so tests cannot
      accidentally inherit developer or CI configuration.

    Rationale:
        SEG tests must be deterministic and must never depend on a real
        `.env` file or shell environment. Any required configuration must
        be provided explicitly by the test or via fixtures.

    Scope:
        This fixture is test-only and MUST NOT be used in production code.
    """
    # ------------------------------------------------------------------
    # 1. Remove all SEG_* variables from the environment
    # ------------------------------------------------------------------
    for key in list(os.environ.keys()):
        if key.startswith("SEG_"):
            monkeypatch.delenv(key, raising=False)

    # ------------------------------------------------------------------
    # 2. Disable `.env` loading for Settings during tests
    # ------------------------------------------------------------------
    try:
        from seg.core.config import Settings

        # Preserve original value to restore after the test
        original_env_file = Settings.model_config.get("env_file", None)

        # Disable dotenv loading explicitly
        monkeypatch.setitem(Settings.model_config, "env_file", None)

    except Exception:
        # If Settings cannot be imported for any reason,
        # fail silently to avoid masking unrelated test failures.
        original_env_file = None

    # Run the test
    yield

    # ------------------------------------------------------------------
    # 3. Restore Settings configuration after the test
    # ------------------------------------------------------------------
    try:
        if original_env_file is not None:
            Settings.model_config["env_file"] = original_env_file
        else:
            Settings.model_config.pop("env_file", None)
    except Exception:  # noqa: S110
        # Never allow cleanup errors to break the test suite
        pass


# ============================================================================
# Base data fixtures
# ============================================================================


@pytest.fixture
def api_token() -> str:
    """Return a deterministic API token for authenticated tests.

    Returns:
        str: API token used in Authorization headers.
    """
    return "66350e905a79c0d0213876cc837624c4a53b2bed2380133a6d27c3e50c40047f"


@pytest.fixture
def sandbox_dir(tmp_path):
    """Create a temporary sandbox directory for filesystem-related tests.

    Args:
        tmp_path: Pytest-provided temporary directory unique to the test.

    Returns:
        Path: Path to the sandbox directory.
    """
    d = tmp_path / "sandbox"
    d.mkdir()
    return d


@pytest.fixture
def allowed_subdirs() -> str:
    """Return a typical CSV of allowlisted subdirectories used in tests.

    Returns:
        str: CSV of allowed subdirectories (for example: "tmp,uploads,output").
    """

    return "tmp,uploads,output,quarantine"


@pytest.fixture
def minimal_safe_env(monkeypatch, sandbox_dir, api_token, allowed_subdirs):
    """Provide a minimal, safe environment for Settings-based tests.

    This fixture sets the three required SEG variables to deterministic
    values so tests don't need to repeat the same `monkeypatch.setenv`
    calls. Tests that need to vary one of these values should accept
    `minimal_safe_env` and then call `monkeypatch.setenv(...)` to
    override the specific variable.
    """
    monkeypatch.setenv("SEG_API_TOKEN", api_token)
    monkeypatch.setenv("SEG_SANDBOX_DIR", str(sandbox_dir))
    monkeypatch.setenv("SEG_ALLOWED_SUBDIRS", allowed_subdirs)
    return {
        "SEG_API_TOKEN": api_token,
        "SEG_SANDBOX_DIR": str(sandbox_dir),
        "SEG_ALLOWED_SUBDIRS": allowed_subdirs,
    }


# ============================================================================
# Settings fixture
# ============================================================================


@pytest.fixture
def settings(api_token, sandbox_dir, allowed_subdirs) -> Settings:
    """Return a minimal, valid Settings object for tests.

    This fixture constructs Settings explicitly via `model_validate`,
    ensuring no configuration is read from the environment or `.env`.

    Args:
        api_token: API token fixture.
        sandbox_dir: Sandbox directory fixture.
        allowed_subdirs: Allowed subdirectories fixture.
    Returns:
        Settings: Fully validated Settings instance.
    """
    return Settings.model_validate(
        {
            "seg_api_token": api_token,
            "seg_sandbox_dir": str(sandbox_dir),
            "seg_allowed_subdirs": allowed_subdirs,
        }
    )


# ============================================================================
# FastAPI app & client fixtures
# ============================================================================


@pytest.fixture
def app(settings):
    """Create a FastAPI application instance configured for tests.

    Args:
        settings: Valid Settings instance injected into the app.

    Returns:
        FastAPI: Configured application instance.
    """
    return create_app(settings)


@pytest.fixture
def client(app):
    """Return a TestClient bound to the configured FastAPI app.

    Args:
        app: FastAPI application fixture.

    Returns:
        TestClient: HTTP client for integration tests.
    """
    return TestClient(app)


# ============================================================================
# HTTP headers
# ============================================================================


@pytest.fixture
def auth_headers(api_token) -> dict[str, str]:
    """Return Authorization headers for authenticated requests.

    Args:
        api_token: API token fixture.

    Returns:
        dict[str, str]: Headers containing a Bearer token.
    """
    return {
        "Authorization": f"Bearer {api_token}",
    }
