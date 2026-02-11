"""
Unit tests for the delete_file action.

These tests freeze filesystem and sandbox invariants:
- deletion is restricted to the sandbox
- symlinks and traversal are rejected
- deletion is idempotent when require_exists is False
- stable error codes are raised for failure cases
"""

from __future__ import annotations

import pytest

from seg.actions.dispatcher import SegActionError
from seg.actions.file.delete import delete_file
from seg.actions.file.schemas import DeleteParams

# ============================================================================
# Successful deletion
# ============================================================================


@pytest.mark.asyncio
async def test_delete_file_existing_file_deleted(
    sandbox_file_factory, minimal_safe_env
):
    """
    GIVEN a file inside an allowed sandbox subdirectory
    WHEN delete_file is called
    THEN the file is deleted and deleted=True is returned
    """
    target = sandbox_file_factory(
        name="to_delete.bin",
        content=b"delete me\n",
    )

    params = DeleteParams(path=str(target.rel_path), require_exists=True)

    result = await delete_file(params)

    assert result.deleted is True
    assert not target.abs_path.exists()


# ============================================================================
# Idempotent behavior
# ============================================================================


@pytest.mark.asyncio
async def test_delete_file_missing_file_idempotent(
    minimal_safe_env,
):
    """
    GIVEN a missing file inside an allowed sandbox subdirectory
    AND require_exists=False
    WHEN delete_file is called
    THEN deleted=False is returned without error
    """
    params = DeleteParams(
        path="tmp/missing.bin",
        require_exists=False,
    )

    result = await delete_file(params)

    assert result.deleted is False


@pytest.mark.asyncio
async def test_delete_file_missing_file_requires_exists(
    minimal_safe_env,
):
    """
    GIVEN a missing file inside an allowed sandbox subdirectory
    AND require_exists=True
    WHEN delete_file is called
    THEN a FILE_NOT_FOUND SegActionError is raised
    """
    params = DeleteParams(
        path="tmp/missing.bin",
        require_exists=True,
    )

    with pytest.raises(SegActionError) as exc:
        await delete_file(params)

    assert exc.value.code == "FILE_NOT_FOUND"


# ============================================================================
# Sandbox and path enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_delete_file_rejects_path_traversal(
    minimal_safe_env,
):
    """
    GIVEN a path attempting directory traversal
    WHEN delete_file is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    params = DeleteParams(
        path="../outside.bin",
        require_exists=True,
    )

    with pytest.raises(SegActionError) as exc:
        await delete_file(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_delete_file_rejects_symlink(sandbox_file_factory, minimal_safe_env):
    """
    GIVEN a symlink inside an allowed sandbox subdirectory
    WHEN delete_file is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
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

    with pytest.raises(SegActionError) as exc:
        await delete_file(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


# ============================================================================
# File type enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_delete_file_rejects_directory(
    minimal_safe_env,
):
    """
    GIVEN a directory inside an allowed sandbox subdirectory
    WHEN delete_file is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
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

    with pytest.raises(SegActionError) as exc:
        await delete_file(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"
