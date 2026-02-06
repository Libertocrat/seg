from __future__ import annotations

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment (Pydantic v2).

    Pydantic-settings maps environment variables from field names by
    default (for example, the field `seg_api_token` maps to the
    environment variable `SEG_API_TOKEN`).

    Attributes:
        seg_api_token: API token required for Bearer authentication.
        seg_fs_root: Filesystem root used by sandboxed actions.
        seg_allowed_subdirs: Raw CSV string of allowed subdirectories.
        seg_max_bytes: Maximum allowed bytes for file operations.
        seg_timeout_ms: Per-request timeout (milliseconds).
        seg_rate_limit_rps: Rate limit in requests-per-second.
        seg_log_level: Logging verbosity.
    """

    seg_api_token: str = Field(...)
    seg_fs_root: str = Field(...)
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
    def allowed_subdirs(self) -> List[str]:
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

    @field_validator("seg_allowed_subdirs", mode="before")
    def _validate_seg_allowed_subdirs(cls, v):
        # Ensure the env value exists and is not empty/whitespace.
        if v is None:
            raise ValueError("SEG_ALLOWED_SUBDIRS must be set and non-empty")
        s = str(v).strip()
        if s == "":
            raise ValueError("SEG_ALLOWED_SUBDIRS must be set and non-empty")
        # Only allow '*' or CSV of simple names (no slashes)
        if s != "*":
            for part in s.split(","):
                name = part.strip()
                if name == "" or "/" in name or name in (".", ".."):
                    raise ValueError(f"Invalid SEG_ALLOWED_SUBDIRS entry: '{part}'")
        return s


# Instantiate settings via `model_validate({})` instead of calling `Settings()`
# directly.
#
# In Pydantic v2, `BaseSettings` always loads configuration from its configured
# sources (environment variables, .env, secrets, etc.) during validation.
# Using `model_validate({})` preserves this runtime behavior while avoiding
# mypy false-positives about missing required constructor arguments for
# settings fields that are populated from the environment.
settings = Settings.model_validate({})
