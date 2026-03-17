"""Runtime configuration loading and validation for SEG."""

from __future__ import annotations

import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import NoReturn

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

SEG_API_TOKEN_SECRET_PATH = Path("/run/secrets/seg_api_token")


def validate_api_token(token: str) -> str:
    """Validate and sanitize SEG_API_TOKEN.

    Rules:
        - Trim surrounding whitespace.
        - Minimum length: 32 characters.
        - Require at least two character classes among lowercase, uppercase,
          digits and symbols.

    Args:
        token: Raw token value from Docker secret or development fallback.

    Returns:
        Sanitized token string.

    Raises:
        ValueError: If the token does not satisfy security constraints.
    """

    sanitized = token.strip()

    if len(sanitized) < 32:
        raise ValueError("SEG_API_TOKEN must be at least 32 characters long")

    classes = 0
    classes += int(any(c.islower() for c in sanitized))
    classes += int(any(c.isupper() for c in sanitized))
    classes += int(any(c.isdigit() for c in sanitized))
    classes += int(any(not c.isalnum() for c in sanitized))

    if classes < 2:
        raise ValueError(
            "SEG_API_TOKEN must contain characters from at least two character classes"
        )

    return sanitized


def load_seg_api_token() -> str:
    """Load SEG_API_TOKEN from Docker secret with development fallback.

    Priority:
        1) /run/secrets/seg_api_token
        2) SEG_API_TOKEN_DEV (only when secret file is missing)

    Returns:
        The trimmed raw token.

    Raises:
        RuntimeError: If secret is missing/empty and fallback is not available.
    """

    try:
        raw_secret = SEG_API_TOKEN_SECRET_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        dev_token = os.getenv("SEG_API_TOKEN_DEV", "").strip()
        if dev_token:
            return dev_token
        raise RuntimeError(
            "SEG_API_TOKEN Docker secret not found at /run/secrets/seg_api_token"
        ) from None

    token = raw_secret.strip()
    if token == "":
        raise RuntimeError("SEG_API_TOKEN Docker secret is empty")

    logger.info("Loaded SEG_API_TOKEN from Docker secret")
    return token


class Settings(BaseSettings):
    """Application settings loaded from environment (Pydantic v2).

    Pydantic-settings maps environment variables from field names by
    default for all settings except `seg_api_token`, which is injected from
    Docker secret during settings initialization.

    Attributes:
        seg_api_token: API token required for Bearer authentication.
        seg_sandbox_dir: Sandbox directory used by sandboxed actions.
        seg_allowed_subdirs: Raw CSV string of allowed subdirectories.
        seg_max_bytes: Maximum allowed bytes for file operations.
        seg_timeout_ms: Per-request timeout (milliseconds).
        seg_rate_limit_rps: Rate limit in requests-per-second.
        seg_log_level: Logging verbosity.
        seg_app_version: Application semantic version (x.y.z).
        seg_enable_docs: Enable OpenAPI docs endpoints.
        seg_enable_security_headers: Enable baseline response security headers.
    """

    # Loaded from Docker secret in `get_settings`, not from environment.
    seg_api_token: str = Field("")
    seg_sandbox_dir: str = Field(...)
    # Read the raw env value as a string to avoid pydantic-settings attempting
    # to JSON-decode a complex type from dotenv. We expose a convenience
    # property `allowed_subdirs` (below) which returns the parsed list.
    # pydantic-settings maps field names to ENV by default
    # (seg_allowed_subdirs -> SEG_ALLOWED_SUBDIRS)
    # `SEG_ALLOWED_SUBDIRS` is required and must be non-empty (CSV or "*")
    seg_allowed_subdirs: str = Field(...)
    seg_max_bytes: int = Field(104857600)
    seg_timeout_ms: int = Field(5000)
    seg_rate_limit_rps: int = Field(10)
    seg_log_level: str = Field("INFO")
    seg_app_version: str = Field("0.1.0")
    seg_enable_docs: bool = Field(False)
    seg_enable_security_headers: bool = Field(True)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        # Ignore unrelated environment variables (e.g. Docker compose metadata)
        # to avoid Pydantic `extra_forbidden` errors when a full .env contains
        # variables that are not part of this Settings model.
        "extra": "ignore",
    }

    @property
    def allowed_subdirs(self) -> list[str]:
        """Return the allowlist as a list of strings parsed from CSV.

        The value is read from the raw environment-backed field
        `seg_allowed_subdirs` which contains a comma-separated list (for
        example: `uploads,output`). Empty or missing values return an empty
        list.

        Returns:
            A list of non-empty, stripped subdirectory names.
        """

        raw = self.seg_allowed_subdirs
        # At this point validation guarantees `raw` is a non-empty string.
        if raw.strip() == "*":
            return ["*"]
        return [p.strip() for p in raw.split(",") if p.strip()]

    @field_validator("seg_sandbox_dir", "seg_allowed_subdirs", mode="before")
    def _validate_required_non_empty(cls, v, info):
        """Reject missing or blank values for required string settings."""

        # Ensure required env values exists and are not empty/whitespace.
        if v is None:
            raise ValueError(f"{info.field_name} must be set and non-empty")
        if isinstance(v, str) and v.strip() == "":
            raise ValueError(f"{info.field_name} must be set and non-empty")
        return v

    @field_validator("seg_allowed_subdirs", mode="before")
    def _validate_seg_allowed_subdirs(cls, v):
        """Validate the raw allowlist format for sandbox subdirectories."""

        s = str(v).strip()
        # Only allow '*' or CSV of simple names (no slashes)
        if s != "*":
            for part in s.split(","):
                name = part.strip()
                if name == "" or "/" in name or name in (".", ".."):
                    raise ValueError(f"Invalid SEG_ALLOWED_SUBDIRS entry: '{part}'")
        return s

    @field_validator("seg_app_version", mode="before")
    def _validate_seg_app_version(cls, v):
        """Validate application version format as semantic version `x.y.z`."""

        s = str(v).strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", s):
            raise ValueError("seg_app_version must use semantic version format x.y.z")
        return s


def abort_config(message: str) -> NoReturn:
    """Log a fatal configuration error and terminate the process."""

    logger.error("Configuration error: %s", message)
    sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    """
    Lazily load and cache application settings from environment sources.

    This accessor intentionally instantiates `Settings` via
    `Settings.model_validate({})` instead of calling `Settings()` directly.

    Rationale:
        - In Pydantic v2, `BaseSettings` loads configuration from its configured
          sources (environment variables, `.env`, secrets, etc.) during
          validation, not during object construction.
        - Calling `model_validate({})` preserves the full runtime behavior of
          environment-based configuration while avoiding mypy false-positives
          about missing required constructor arguments.
        - Deferring settings instantiation avoids loading configuration at
          import time, which is critical for test isolation and for preventing
          failures when required environment variables are not yet defined.

    Design considerations:
        - Settings are loaded lazily and cached to provide a single source of
          truth at runtime.
        - Tests can fully control configuration by setting environment
          variables before invoking this function.
        - Importing application modules never implicitly depends on the
          presence of environment configuration.

    Returns:
        Settings: A fully validated Settings instance loaded from the current
        environment and Docker secret sources.
    """
    try:
        settings = Settings.model_validate({})
        token = load_seg_api_token()
        settings.seg_api_token = validate_api_token(token)
        return settings
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        abort_config(str(exc))
