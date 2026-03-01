"""Export SEG OpenAPI schema to a JSON file.

This script builds the application using create_app()
and writes the generated OpenAPI schema to disk.

Intended for CI usage.
"""

from __future__ import annotations

import json
from pathlib import Path

from seg.app import create_app
from seg.core.config import Settings

OPENAPI_OUTPUT_PATH = Path("docs/api-docs/output/openapi.json")


# Minimal valid settings for schema generation; values won't affect the schema but must
# satisfy validation. We set `seg_enable_docs=True` to ensure the schema includes
# the docs endpoints.
def build_docs_settings() -> Settings:
    return Settings(
        seg_log_level="INFO",
        seg_api_token="docs-token",  # noqa: S106 -- fixed token for documentation purposes only
        seg_sandbox_dir="/seg",
        seg_allowed_subdirs="tmp",
        seg_enable_docs=True,
        seg_max_bytes=1048576,
        seg_timeout_ms=5000,
        seg_rate_limit_rps=5,
    )


def main() -> None:
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
