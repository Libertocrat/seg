"""Export SEG OpenAPI schema to a JSON file.

This script builds the application using create_app()
and writes the generated OpenAPI schema to disk.

Intended for CI usage.
"""

from __future__ import annotations

import json
from pathlib import Path

from seg.app import create_app

OPENAPI_OUTPUT_PATH = Path("docs/api-docs/output/openapi.json")


def main() -> None:
    app = create_app()
    schema = app.openapi()

    output_path = OPENAPI_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
