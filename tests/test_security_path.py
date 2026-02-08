# tests/test_security_path.py
"""
Tests for filesystem path security helpers.

These tests freeze the security invariants that define SEG's sandbox model.
They verify that SEG never escapes its sandbox, never follows symlinks,
and rejects malformed or dangerous paths.
"""

import os

import pytest

from seg.core.security.paths import (
    PathSecurityError,
    resolve_in_sandbox,
    safe_open_no_follow,
    sanitize_rel_path,
)

# ============================================================================
# sanitize_rel_path – syntactic security
# ============================================================================


def test_sanitize_rejects_empty_path():
    """
    GIVEN an empty user path
    WHEN sanitize_rel_path is called
    THEN a PathSecurityError is raised
    """
    with pytest.raises(PathSecurityError):
        sanitize_rel_path("")


def test_sanitize_rejects_absolute_path():
    """
    GIVEN an absolute user path
    WHEN sanitize_rel_path is called
    THEN a PathSecurityError is raised
    """
    with pytest.raises(PathSecurityError):
        sanitize_rel_path("/etc/passwd")


def test_sanitize_rejects_traversal():
    """
    GIVEN a path containing '..'
    WHEN sanitize_rel_path is called
    THEN a PathSecurityError is raised
    """
    with pytest.raises(PathSecurityError):
        sanitize_rel_path("../secret.txt")


def test_sanitize_rejects_backslashes():
    """
    GIVEN a path containing backslashes
    WHEN sanitize_rel_path is called
    THEN a PathSecurityError is raised
    """
    with pytest.raises(PathSecurityError):
        sanitize_rel_path("..\\secret.txt")


def test_sanitize_rejects_control_characters():
    """
    GIVEN a path containing control characters
    WHEN sanitize_rel_path is called
    THEN a PathSecurityError is raised
    """
    with pytest.raises(PathSecurityError):
        sanitize_rel_path("bad\x00path")


def test_sanitize_normalizes_valid_path():
    """
    GIVEN a valid relative path with redundant segments
    WHEN sanitize_rel_path is called
    THEN the path is normalized and safe
    """
    p = sanitize_rel_path("uploads/./files/test.txt")

    assert p == "uploads/files/test.txt"


# ============================================================================
# resolve_in_sandbox – sandbox boundary enforcement
# ============================================================================


def test_resolve_path_inside_sandbox(tmp_path, monkeypatch):
    """
    GIVEN a valid relative path inside the sandbox
    WHEN resolve_in_sandbox is called
    THEN the resolved path is inside the sandbox directory
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    (sandbox / "uploads").mkdir()
    (sandbox / "uploads" / "file.txt").touch()

    monkeypatch.setattr(
        "seg.core.security.paths.settings.seg_allowed_subdirs",
        "uploads",
    )

    resolved = resolve_in_sandbox(sandbox, "uploads/file.txt")

    assert resolved.exists()
    assert resolved.is_file()
    assert str(resolved).startswith(str(sandbox))


def test_resolve_rejects_path_outside_sandbox(tmp_path, monkeypatch):
    """
    GIVEN a path that would escape the sandbox
    WHEN resolve_in_sandbox is called
    THEN a PathSecurityError is raised
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    monkeypatch.setattr(
        "seg.core.security.paths.settings.seg_allowed_subdirs",
        "uploads",
    )

    with pytest.raises(PathSecurityError):
        resolve_in_sandbox(sandbox, "../outside.txt")


def test_resolve_rejects_disallowed_subdir(tmp_path, monkeypatch):
    """
    GIVEN a path whose first component is not in the allowlist
    WHEN resolve_in_sandbox is called
    THEN a PathSecurityError is raised
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "secret").mkdir()

    monkeypatch.setattr(
        "seg.core.security.paths.settings.seg_allowed_subdirs",
        "uploads",
    )

    with pytest.raises(PathSecurityError):
        resolve_in_sandbox(sandbox, "secret/file.txt")


def test_resolve_rejects_symlink_component(tmp_path, monkeypatch):
    """
    GIVEN a path containing a symlink component
    WHEN resolve_in_sandbox is called
    THEN a PathSecurityError is raised
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    real_dir = tmp_path / "real"
    real_dir.mkdir()

    symlink = sandbox / "uploads"
    symlink.symlink_to(real_dir)

    monkeypatch.setattr(
        "seg.core.security.paths.settings.seg_allowed_subdirs",
        "uploads",
    )

    with pytest.raises(PathSecurityError):
        resolve_in_sandbox(sandbox, "uploads/file.txt")


def test_resolve_allows_any_subdir_when_wildcard(tmp_path, monkeypatch):
    """
    GIVEN `SEG_ALLOWED_SUBDIRS` is set to "*"
    WHEN resolving a path whose first component is arbitrary
    THEN the path is allowed as long as it remains under the sandbox
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    (sandbox / "other").mkdir()
    (sandbox / "other" / "file.txt").touch()

    monkeypatch.setattr(
        "seg.core.security.paths.settings.seg_allowed_subdirs",
        "*",
    )

    resolved = resolve_in_sandbox(sandbox, "other/file.txt")

    assert resolved.exists()
    assert resolved.is_file()
    assert str(resolved).startswith(str(sandbox))


def test_resolve_rejects_missing_sandbox_dir(tmp_path):
    """
    GIVEN a non-existent sandbox directory
    WHEN resolve_in_sandbox is called
    THEN a PathSecurityError is raised
    """
    missing = tmp_path / "does-not-exist"

    with pytest.raises(PathSecurityError):
        resolve_in_sandbox(missing, "file.txt")


# ============================================================================
# safe_open_no_follow – secure file opening
# ============================================================================


def test_safe_open_allows_regular_file(tmp_path):
    """
    GIVEN a regular file inside the sandbox
    WHEN safe_open_no_follow is used
    THEN the file descriptor is returned successfully
    """
    f = tmp_path / "file.txt"
    f.write_text("hello")

    fd = safe_open_no_follow(f, os.O_RDONLY)
    try:
        assert fd >= 0
    finally:
        os.close(fd)


def test_safe_open_rejects_symlink(tmp_path):
    """
    GIVEN a symlink pointing to a file
    WHEN safe_open_no_follow is used
    THEN a PathSecurityError is raised
    """
    target = tmp_path / "real.txt"
    target.write_text("secret")

    link = tmp_path / "link.txt"
    link.symlink_to(target)

    with pytest.raises(PathSecurityError):
        safe_open_no_follow(link, os.O_RDONLY)


def test_safe_open_rejects_non_regular_file(tmp_path):
    """
    GIVEN a directory path
    WHEN safe_open_no_follow is used
    THEN a PathSecurityError is raised
    """
    d = tmp_path / "dir"
    d.mkdir()

    with pytest.raises(PathSecurityError):
        safe_open_no_follow(d, os.O_RDONLY)
