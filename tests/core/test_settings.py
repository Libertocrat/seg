"""Tests for `seg.core.config.Settings`.

These tests check loading from environment, defaults and validation
invariants for SEG configuration.
"""

import pytest
from pydantic import ValidationError

from seg.core.config import Settings

# ===========================================================================
# Happy path
# ===========================================================================


def test_settings_load_from_env(minimal_safe_env, api_token, sandbox_dir):
    """
    GIVEN the minimal required environment variables are set
    WHEN the Settings are validated from the environment
    THEN the resulting `Settings` object contains the expected values
    """
    s = Settings.model_validate({})

    assert s.seg_api_token == api_token
    assert s.seg_sandbox_dir == str(sandbox_dir)
    assert s.seg_allowed_subdirs == "tmp,uploads,output,quarantine"
    assert s.allowed_subdirs == ["tmp", "uploads", "output", "quarantine"]


def test_settings_defaults_applied(minimal_safe_env):
    """
    GIVEN the minimal required environment variables are set
    WHEN the Settings are validated
    THEN default values are applied for optional integer/string fields
    """
    s = Settings.model_validate({})

    assert s.seg_max_bytes == 104857600
    assert s.seg_timeout_ms == 5000
    assert s.seg_rate_limit_rps == 10
    assert s.seg_log_level == "INFO"


# ===========================================================================
# Required variables
# ===========================================================================


@pytest.mark.parametrize(
    "missing_var",
    [
        "SEG_API_TOKEN",
        "SEG_SANDBOX_DIR",
        "SEG_ALLOWED_SUBDIRS",
    ],
)
def test_missing_required_env_raises(minimal_safe_env, monkeypatch, missing_var):
    """
    GIVEN one of the required environment variables is empty/missing
    WHEN Settings are validated
    THEN a ValidationError is raised
    """
    # minimal_safe_env provides the baseline, then we simulate missing
    # by setting the variable to an empty string.
    monkeypatch.setenv(missing_var, "")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


# ===========================================================================
# Variables datatype validation
# ===========================================================================


@pytest.mark.parametrize(
    "env_field",
    [
        "SEG_MAX_BYTES",
        "SEG_TIMEOUT_MS",
        "SEG_RATE_LIMIT_RPS",
    ],
)
def test_int_fields_invalid_string(minimal_safe_env, monkeypatch, env_field):
    """
    GIVEN any integer-backed environment field set to a non-integer string
    WHEN Settings are validated
    THEN a ValidationError is raised for that field
    """
    # Provide a clearly non-integer string
    monkeypatch.setenv(env_field, "123abc")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


# ===========================================================================
# SEG_ALLOWED_SUBDIRS parsing
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        ("*", ["*"]),
        ("scripts", ["scripts"]),
        ("scripts,output", ["scripts", "output"]),
        (" scripts , output ", ["scripts", "output"]),
    ],
)
def test_allowed_subdirs_valid(minimal_safe_env, monkeypatch, value, expected):
    """
    GIVEN various valid values for SEG_ALLOWED_SUBDIRS (CSV or "*")
    WHEN Settings parses the value
    THEN `allowed_subdirs` returns the expected list
    """
    # override allowed_subdirs for this case
    monkeypatch.setenv("SEG_ALLOWED_SUBDIRS", value)

    s = Settings.model_validate({})

    assert s.allowed_subdirs == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        ".",
        "..",
        "scripts,/bin",
        "scripts,../etc",
        "scripts,,output",
    ],
)
def test_allowed_subdirs_invalid(minimal_safe_env, monkeypatch, value):
    """
    GIVEN malformed or prohibited SEG_ALLOWED_SUBDIRS values
    WHEN Settings attempts to validate the value
    THEN validation fails with ValidationError
    """
    monkeypatch.setenv("SEG_ALLOWED_SUBDIRS", value)

    with pytest.raises(ValidationError):
        Settings.model_validate({})
