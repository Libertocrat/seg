"""
Unit tests for the file_delete action.

These tests freeze filesystem and sandbox invariants:
- deletion is restricted to the sandbox
- symlinks and traversal are rejected
- deletion is idempotent when require_exists is False
- stable error codes are raised for failure cases
"""

from __future__ import annotations

import pytest

from seg.actions.file.delete import file_delete
from seg.actions.file.schemas import DeleteParams
from seg.core.errors import FILE_NOT_FOUND, PATH_NOT_ALLOWED, SegError

# ============================================================================
# Successful Deletion
# ============================================================================


@pytest.mark.asyncio
async def test_file_delete_existing_file_deleted(
    sandbox_file_factory, minimal_safe_env
):
    """
    GIVEN a file inside an allowed sandbox subdirectory
    WHEN file_delete is called
    THEN the file is deleted and deleted=True is returned
    """
    target = sandbox_file_factory(
        name="to_delete.bin",
        content=b"delete me\n",
    )

    params = DeleteParams(path=str(target.rel_path), require_exists=True)

    result = await file_delete(params)

    assert result.deleted is True
    assert not target.abs_path.exists()


# ============================================================================
# Idempotent Behavior
# ============================================================================


@pytest.mark.asyncio
async def test_file_delete_missing_file_idempotent(
    minimal_safe_env,
):
    """
    GIVEN a missing file inside an allowed sandbox subdirectory
    AND require_exists=False
    WHEN file_delete is called
    THEN deleted=False is returned without error
    """
    params = DeleteParams(
        path="tmp/missing.bin",
        require_exists=False,
    )

    result = await file_delete(params)

    assert result.deleted is False


@pytest.mark.asyncio
async def test_file_delete_missing_file_requires_exists(
    minimal_safe_env,
):
    """
    GIVEN a missing file inside an allowed sandbox subdirectory
    AND require_exists=True
    WHEN file_delete is called
    THEN a FILE_NOT_FOUND SegError is raised
    """
    params = DeleteParams(
        path="tmp/missing.bin",
        require_exists=True,
    )

    with pytest.raises(SegError) as exc:
        await file_delete(params)

    assert exc.value.code == FILE_NOT_FOUND.code


# ============================================================================
# Sandbox and Path Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_delete_rejects_path_traversal(
    minimal_safe_env,
):
    """
    GIVEN a path attempting directory traversal
    WHEN file_delete is called
    THEN a PATH_NOT_ALLOWED SegError is raised
    """
    params = DeleteParams(
        path="../outside.bin",
        require_exists=True,
    )

    with pytest.raises(SegError) as exc:
        await file_delete(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


@pytest.mark.asyncio
async def test_file_delete_rejects_symlink(sandbox_file_factory, minimal_safe_env):
    """
    GIVEN a symlink inside an allowed sandbox subdirectory
    WHEN file_delete is called
    THEN a PATH_NOT_ALLOWED SegError is raised
    """
    target = sandbox_file_factory(
        name="target.bin",
        content=b"delete me\n",
    )
    symlink = target.abs_path.parent / "link.bin"
    symlink.symlink_to(target.abs_path)

    relative_path = str(target.rel_path.parent / symlink.name)

    params = DeleteParams(
        path=relative_path,
        require_exists=True,
    )

    with pytest.raises(SegError) as exc:
        await file_delete(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


# ============================================================================
# File type enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_delete_rejects_directory(
    minimal_safe_env,
):
    """
    GIVEN a directory inside an allowed sandbox subdirectory
    WHEN file_delete is called
    THEN a PATH_NOT_ALLOWED SegError is raised
    """
    from pathlib import Path

    sandbox = Path(minimal_safe_env["SEG_SANDBOX_DIR"])
    allowed = minimal_safe_env["SEG_ALLOWED_SUBDIRS"].split(",")

    allowed_dir = sandbox / allowed[0]
    allowed_dir.mkdir(parents=True, exist_ok=True)

    directory = allowed_dir / "subdir"
    directory.mkdir()

    params = DeleteParams(
        path=f"{allowed[0]}/subdir",
        require_exists=True,
    )

    with pytest.raises(SegError) as exc:
        await file_delete(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code
