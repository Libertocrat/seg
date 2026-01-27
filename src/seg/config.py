from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment (Pydantic v2).

    Field-level `env` metadata is intentionally omitted because
    pydantic-settings maps environment variables from field names
    by default (e.g. `seg_api_token` -> `SEG_API_TOKEN`).
    """

    seg_api_token: str = Field(...)
    seg_fs_root: str = Field(...)
    # Read the raw env value as a string to avoid pydantic-settings attempting
    # to JSON-decode a complex type from dotenv. We expose a convenience
    # property `allowed_subdirs` (below) which returns the parsed list.
    seg_allowed_subdirs: str | None = Field(None, env="SEG_ALLOWED_SUBDIRS")
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

        This supports the common `.env` format `uploads,output` while keeping
        runtime compatibility with pydantic-settings dotenv loader.
        """
        raw = self.seg_allowed_subdirs
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]
