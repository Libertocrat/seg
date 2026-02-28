"""Build versioned Swagger documentation site for GitHub Pages.

This script:
- Receives the current release version (e.g. v0.1.0)
- Copies existing site content (if available)
- Adds a new version folder under /api-docs/<version>/
- Updates /api-docs/ to redirect to latest
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

TEMPLATE_DIR = Path("docs/api-docs/template")
TEMPLATE_NAME = "swagger.html"
OPENAPI_OUTPUT_PATH = Path("docs/api-docs/output/openapi.json")


def main() -> None:
    version = os.environ["RELEASE_VERSION"]

    site_root = Path("site")
    api_docs_root = site_root / "api-docs"
    version_dir = api_docs_root / version

    template_dir = TEMPLATE_DIR
    openapi_path = OPENAPI_OUTPUT_PATH

    api_docs_root.mkdir(parents=True, exist_ok=True)
    version_dir.mkdir(parents=True, exist_ok=True)

    # Copy Swagger UI assets (already installed in node_modules)
    swagger_dist = Path("node_modules/swagger-ui-dist")
    shutil.copytree(swagger_dist, version_dir, dirs_exist_ok=True)

    # Copy template as index.html
    shutil.copy(template_dir / TEMPLATE_NAME, version_dir / "index.html")

    # Copy OpenAPI spec
    shutil.copy(openapi_path, version_dir / "openapi.json")

    # Create latest redirect
    latest_index = api_docs_root / "index.html"
    latest_index.write_text(
        f'<meta http-equiv="refresh" content="0; url=./{version}/" />\n',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
