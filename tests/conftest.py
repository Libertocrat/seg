"""
Global pytest fixtures for SEG test suite.

This module defines shared fixtures used across unit, integration, and
smoke tests. The primary goals are:

- Ensure full isolation from the local environment (.env, shell variables).
- Provide minimal, valid defaults for Settings-dependent tests.
- Enable authenticated HTTP requests against the FastAPI app.
"""

from __future__ import annotations

import gzip
import os
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seg.core.config import Settings

# ============================================================================
# Environment and registry isolation
# ============================================================================


@pytest.fixture(autouse=True)
def clean_seg_environment(monkeypatch):
    """Ensure test-only isolation from local configuration sources.

    This fixture enforces *strict configuration isolation* for all tests by:

    - Removing any `SEG_*` variables from the process environment.
    - Disabling `.env` file loading in `Settings`.
    - Clearing the cached Settings instance (`get_settings`) so each test
      observes only the environment prepared by its fixtures.

    Rationale:
        SEG settings are lazily loaded and cached via `get_settings()`.
        Without clearing the cache, changes to environment variables
        performed by fixtures would not take effect consistently.

        This fixture guarantees that:
        - No test depends on developer or CI `.env` files.
        - No test depends on execution order.
        - Every test sees a fresh Settings resolution.

    Scope:
        Test-only fixture. MUST NOT be used in production code.
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
    original_env_file = None
    try:
        from seg.core.config import Settings

        original_env_file = Settings.model_config.get("env_file", None)
        monkeypatch.setitem(Settings.model_config, "env_file", None)
    except Exception:  # noqa: S110
        # Never fail tests due to configuration import issues
        pass

    # ------------------------------------------------------------------
    # 3. Clear cached settings to ensure fresh resolution per test
    # ------------------------------------------------------------------
    try:
        from seg.core.config import get_settings

        get_settings.cache_clear()
    except Exception:  # noqa: S110
        pass

    # Run the test
    yield

    # ------------------------------------------------------------------
    # 4. Restore Settings configuration after the test
    # ------------------------------------------------------------------
    try:
        if original_env_file is not None:
            Settings.model_config["env_file"] = original_env_file
        else:
            Settings.model_config.pop("env_file", None)
    except Exception:  # noqa: S110
        pass


@pytest.fixture
def clean_action_registry():
    """
    GIVEN a global in-memory action registry
    WHEN a test needs registry isolation
    THEN it runs with an empty registry and baseline is restored afterward.
    """
    from seg.actions import registry

    # Use the public registry API: take a snapshot, replace with an empty
    # registry for the duration of the test, and restore the snapshot after.
    snapshot = registry.get_registry_snapshot()
    registry.replace_registry({})
    try:
        yield
    finally:
        registry.restore_registry(snapshot)


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
    # Ensure allowed subdirectories exist to simulate a mounted volume with
    # pre-created directories. This matches production behavior where the
    # allowed subdirs are present ahead of file operations like move.
    for sub in allowed_subdirs.split(","):
        (sandbox_dir / sub).mkdir(parents=True, exist_ok=True)
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
    from seg.app import create_app

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


# ============================================================================
# Filesystem fixtures
# ============================================================================


@dataclass(frozen=True)
class SandboxFile:
    """
    Value object representing a file created inside the SEG sandbox for tests.

    This object intentionally exposes multiple path representations to avoid
    leaking sandbox layout logic into individual tests.

    Attributes:
        abs_path:
            Absolute filesystem path to the file on disk.
            Intended for assertions that require direct filesystem access
            (existence checks, debugging, etc.).

        rel_path:
            Path relative to the sandbox root.
            This is the form expected by SEG actions and MUST be used when
            constructing execute request payloads.

        subdir:
            The sandbox subdirectory in which the file was created.
            Provided for clarity and debugging; tests should rarely need it.
    """

    abs_path: Path
    rel_path: Path
    subdir: str


@pytest.fixture
def sandbox_file_factory(minimal_safe_env):
    """
    Factory fixture to create files inside the SEG sandbox for tests.

    This fixture encapsulates all sandbox layout knowledge and returns a
    SandboxFile value object exposing both absolute and sandbox-relative paths.

    Tests MUST use `SandboxFile.rel_path` when passing paths to SEG actions,
    and SHOULD avoid performing manual path manipulation.

    Returns:
        Callable[[name, content, subdir], SandboxFile]
    """

    sandbox = Path(minimal_safe_env["SEG_SANDBOX_DIR"])
    allowed = minimal_safe_env["SEG_ALLOWED_SUBDIRS"].split(",")

    def _create(
        name: str,
        content: bytes,
        subdir: str | None = None,
    ) -> SandboxFile:
        chosen = subdir or allowed[0]
        base = sandbox / chosen
        base.mkdir(parents=True, exist_ok=True)

        abs_path = base / name
        abs_path.write_bytes(content)

        rel_path = abs_path.relative_to(sandbox)
        return SandboxFile(
            abs_path=abs_path,
            rel_path=rel_path,
            subdir=chosen,
        )

    return _create


# ============================================================================
# Higher-level file factory for MIME tests
# ============================================================================


@pytest.fixture
def file_factory(sandbox_file_factory):
    """
    High-level factory to generate realistic files by logical type.

    This fixture builds real, structurally valid files for common MIME types
    without introducing external dependencies.

    Supported types:
        - "text"
        - "md"
        - "csv"
        - "png"
        - "pdf"
        - "zip"
        - "tar"
        - "gzip"
        - "exe"
        - "elf"
        - "shell"
        - "python"
        - "javascript"

    Returns:
        Callable[[file_type: str, name: str], SandboxFile]
    """

    def create(file_type: str, name: str) -> SandboxFile:
        file_type = file_type.lower()

        # ------------------------------------------------------------------
        # TEXT
        # ------------------------------------------------------------------
        if file_type == "text":
            return sandbox_file_factory(
                name=name,
                content=b"Hello SEG\n",
            )

        # ------------------------------------------------------------------
        # MD
        # ------------------------------------------------------------------
        if file_type == "md":
            md_bytes = (
                b"# SEG Test Document\n\n"
                b"This is a markdown file.\n\n"
                b"- item 1\n"
                b"- item 2\n"
            )
            return sandbox_file_factory(name=name, content=md_bytes)

        # ------------------------------------------------------------------
        # CSV
        # ------------------------------------------------------------------
        if file_type == "csv":
            csv_bytes = b"id,name,value\n1,alpha,100\n2,beta,200\n"
            return sandbox_file_factory(name=name, content=csv_bytes)

        # ------------------------------------------------------------------
        # PNG (minimal valid PNG)
        # ------------------------------------------------------------------
        if file_type == "png":
            png_bytes = (
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01"
                b"\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00"
                b"\x90wS\xde"
                b"\x00\x00\x00\x0aIDAT"
                b"\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00"
                b"\x18\xdd\x8d\x18"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            return sandbox_file_factory(name=name, content=png_bytes)

        # ------------------------------------------------------------------
        # PDF (minimal valid PDF)
        # ------------------------------------------------------------------
        if file_type == "pdf":
            pdf_bytes = (
                b"%PDF-1.4\n"
                b"1 0 obj\n"
                b"<< /Type /Catalog >>\n"
                b"endobj\n"
                b"trailer\n"
                b"<< /Root 1 0 R >>\n"
                b"%%EOF"
            )
            return sandbox_file_factory(name=name, content=pdf_bytes)

        # ------------------------------------------------------------------
        # ZIP
        # ------------------------------------------------------------------
        if file_type == "zip":
            # First create empty placeholder
            sf = sandbox_file_factory(name=name, content=b"")
            with zipfile.ZipFile(sf.abs_path, "w") as z:
                z.writestr("data.bin", os.urandom(256))
            return sf

        # ------------------------------------------------------------------
        # TAR
        # ------------------------------------------------------------------
        if file_type == "tar":
            sf = sandbox_file_factory(name=name, content=b"")
            temp_file = sf.abs_path.parent / "data.bin"
            temp_file.write_bytes(os.urandom(256))
            with tarfile.open(sf.abs_path, "w") as t:
                t.add(temp_file, arcname="data.bin")
            temp_file.unlink()
            return sf

        # ------------------------------------------------------------------
        # GZIP
        # ------------------------------------------------------------------
        if file_type == "gzip":
            sf = sandbox_file_factory(name=name, content=b"")
            with gzip.open(sf.abs_path, "wb") as g:
                g.write(os.urandom(256))
            return sf

        # ------------------------------------------------------------------
        # EXE (Windows PE / DOS MZ header)
        # ------------------------------------------------------------------
        if file_type == "exe":
            exe_bytes = b"MZ" + b"\x00" * 512
            return sandbox_file_factory(name=name, content=exe_bytes)

        # ------------------------------------------------------------------
        # ELF (Linux executable)
        # ------------------------------------------------------------------
        if file_type == "elf":
            elf_bytes = (
                b"\x7fELF"  # Magic
                + b"\x02"  # EI_CLASS (64-bit)
                + b"\x01"  # EI_DATA (little endian)
                + b"\x01"  # EI_VERSION
                + (b"\x00" * 9)  # EI_PAD
                + b"\x02\x00"  # e_type (EXEC)
                + b"\x3e\x00"  # e_machine (x86-64)
                + b"\x01\x00\x00\x00"  # e_version
                + (b"\x00" * 52)
            )
            return sandbox_file_factory(name=name, content=elf_bytes)

        # ------------------------------------------------------------------
        # SHELL SCRIPT
        # ------------------------------------------------------------------
        if file_type == "shell":
            shell_bytes = b"#!/bin/bash\n echo SEG\n"
            return sandbox_file_factory(name=name, content=shell_bytes)

        # ------------------------------------------------------------------
        # PYTHON SCRIPT
        # ------------------------------------------------------------------
        if file_type == "python":
            py_bytes = b"#!/usr/bin/env python3\nprint('SEG')\n"
            return sandbox_file_factory(name=name, content=py_bytes)

        # ------------------------------------------------------------------
        # JAVASCRIPT
        # ------------------------------------------------------------------
        if file_type == "javascript":
            js_bytes = b"#!/usr/bin/env node\nconsole.log('SEG');\n"
            return sandbox_file_factory(name=name, content=js_bytes)

        raise ValueError(f"Unsupported file type: {file_type}")

    return create
