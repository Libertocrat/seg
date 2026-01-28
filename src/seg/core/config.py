from __future__ import annotations

from typing import List

from pydantic import Field
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
    seg_allowed_subdirs: str | None = Field(default=None)
    seg_max_bytes: int = Field(104857600)
    seg_timeout_ms: int = Field(5000)
    seg_rate_limit_rps: int = Field(10)
    seg_log_level: str = Field("INFO")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
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
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]


# Module-level singleton for convenience and discoverability. Importers
# can use `from seg.core import settings` to access validated app config.
settings = Settings()
