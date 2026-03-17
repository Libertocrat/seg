"""Export SEG OpenAPI schema to a JSON file.

This script builds the application using create_app()
and writes the generated OpenAPI schema to disk.

Intended for CI usage.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from seg.app import create_app
from seg.core.config import Settings

OPENAPI_OUTPUT_PATH = Path("docs/api-docs/output/openapi.json")


def get_release_version() -> str:
    """Return the normalized release version for documentation assets.

    Returns:
        Semantic version string without a leading `v` prefix.

    Raises:
        ValueError: If `RELEASE_VERSION` is not a valid semantic version.
    """

    raw = os.getenv("RELEASE_VERSION", "0.1.0").strip()
    normalized = raw[1:] if raw.startswith("v") else raw
    if not re.fullmatch(r"\d+\.\d+\.\d+", normalized):
        raise ValueError(
            "RELEASE_VERSION must be in format vX.Y.Z or X.Y.Z (for example: v1.2.3)"
        )
    return normalized


# Minimal valid settings for schema generation; values won't affect the schema but must
# satisfy validation. We set `seg_enable_docs=True` to ensure the schema includes
# the docs endpoints.
def build_docs_settings() -> Settings:
    """Create a minimal settings object for documentation generation.

    Returns:
        Valid application settings suitable for OpenAPI export.
    """

    return Settings(
        seg_log_level="INFO",
        seg_app_version=get_release_version(),
        seg_api_token="docs-token",  # noqa: S106 -- fixed token for documentation purposes only
        seg_sandbox_dir="/seg",
        seg_allowed_subdirs="tmp",
        seg_enable_docs=True,
        seg_max_bytes=1048576,
        seg_timeout_ms=5000,
        seg_rate_limit_rps=5,
        seg_enable_security_headers=True,
    )


def main() -> None:
    """Export the generated OpenAPI schema to the docs output path."""

    app = create_app(settings=build_docs_settings())
    schema = app.openapi()

    output_path = OPENAPI_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
