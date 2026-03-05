"""Unit tests for the file_move action.

These tests freeze filesystem, sandbox, and policy invariants:
- source and destination must stay inside sandbox
- symlinks and traversal are rejected
- extension changes are forbidden
- overwrite policy is strictly enforced
- only regular files are movable
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seg.actions.exceptions import SegActionError
from seg.actions.file.move import file_move
from seg.actions.file.schemas import FileMoveParams
from seg.core.errors import CONFLICT, FILE_NOT_FOUND, PATH_NOT_ALLOWED

# ============================================================================
# Successful Move Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_file_move_success_same_directory_rename(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a source file inside an allowed sandbox subdirectory
    AND a destination path in the same subdirectory with same extension
    WHEN file_move is called
    THEN moved=True and the file exists only at destination
    """
    source = sandbox_file_factory(
        name="source.txt",
        content=b"hello move\n",
    )

    destination_rel = source.rel_path.parent / "renamed.txt"
    destination_abs = source.abs_path.parent / "renamed.txt"

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination_rel),
        overwrite=False,
    )

    result = await file_move(params)

    assert result.moved is True
    assert result.source == str(source.rel_path)
    assert result.destination == str(destination_rel)
    assert not source.abs_path.exists()
    assert destination_abs.exists()


@pytest.mark.asyncio
async def test_file_move_success_cross_directory(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a source file in one allowed subdirectory
    AND a destination in a different allowed subdirectory with same extension
    WHEN file_move is called
    THEN the move succeeds and file exists only at destination
    """
    allowed = minimal_safe_env["SEG_ALLOWED_SUBDIRS"].split(",")
    assert len(allowed) >= 2
    src_subdir, dst_subdir = allowed[0], allowed[1]

    source = sandbox_file_factory(
        name="cross.bin",
        content=b"cross-dir\n",
        subdir=src_subdir,
    )

    destination_rel = Path(dst_subdir) / "cross.bin"
    sandbox = Path(minimal_safe_env["SEG_SANDBOX_DIR"])
    destination_abs = sandbox / destination_rel

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination_rel),
        overwrite=False,
    )

    result = await file_move(params)

    assert result.moved is True
    assert not source.abs_path.exists()
    assert destination_abs.exists()


@pytest.mark.asyncio
async def test_file_move_success_overwrite_true(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a source file and an existing destination regular file
    AND overwrite=True
    WHEN file_move is called
    THEN destination content is replaced, source is removed, and moved=True
    """
    source = sandbox_file_factory(
        name="payload.txt",
        content=b"SOURCE_BYTES",
    )
    destination = sandbox_file_factory(
        name="existing.txt",
        content=b"OLD_DEST_BYTES",
        subdir=source.subdir,
    )

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination.rel_path),
        overwrite=True,
    )

    result = await file_move(params)

    assert result.moved is True
    assert not source.abs_path.exists()
    assert destination.abs_path.exists()
    assert destination.abs_path.read_bytes() == b"SOURCE_BYTES"


# ============================================================================
# Overwrite policy enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_move_conflict_when_destination_exists_and_overwrite_false(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a source file and an existing destination regular file
    AND overwrite=False
    WHEN file_move is called
    THEN a CONFLICT SegActionError is raised
    """
    source = sandbox_file_factory(
        name="source.txt",
        content=b"SRC",
    )
    destination = sandbox_file_factory(
        name="dest.txt",
        content=b"DST",
        subdir=source.subdir,
    )

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination.rel_path),
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == CONFLICT.code


# ============================================================================
# Extension policy enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_move_rejects_extension_change(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a source file and destination path with different extension
    WHEN file_move is called
    THEN a CONFLICT SegActionError is raised
    """
    source = sandbox_file_factory(
        name="file.txt",
        content=b"content",
    )
    destination_rel = source.rel_path.parent / "file.pdf"

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination_rel),
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == CONFLICT.code


# ============================================================================
# Sandbox enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_move_rejects_source_path_traversal(
    minimal_safe_env,
):
    """
    GIVEN a source path with traversal
    WHEN file_move is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    params = FileMoveParams(
        source_path="../outside.bin",
        destination_path="tmp/outside.bin",
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


@pytest.mark.asyncio
async def test_file_move_rejects_destination_path_traversal(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a valid source file
    AND a destination path with traversal
    WHEN file_move is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    source = sandbox_file_factory(
        name="source.bin",
        content=b"source",
    )

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path="../outside.bin",
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


@pytest.mark.asyncio
async def test_file_move_rejects_symlink_source(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a valid file and a symlink pointing to it
    WHEN source_path is the symlink and file_move is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    target = sandbox_file_factory(
        name="target.bin",
        content=b"target",
    )
    symlink_abs = target.abs_path.parent / "source_link.bin"
    symlink_abs.symlink_to(target.abs_path)

    symlink_rel = target.rel_path.parent / symlink_abs.name
    destination_rel = target.rel_path.parent / "dest.bin"

    params = FileMoveParams(
        source_path=str(symlink_rel),
        destination_path=str(destination_rel),
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


@pytest.mark.asyncio
async def test_file_move_rejects_symlink_destination(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a valid source file
    AND destination path set to an existing symlink
    WHEN file_move is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    source = sandbox_file_factory(
        name="source.bin",
        content=b"source",
    )
    target = sandbox_file_factory(
        name="target.bin",
        content=b"target",
        subdir=source.subdir,
    )

    dest_link_abs = source.abs_path.parent / "dest_link.bin"
    dest_link_abs.symlink_to(target.abs_path)
    dest_link_rel = source.rel_path.parent / dest_link_abs.name

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(dest_link_rel),
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


# ============================================================================
# File existence & type enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_move_rejects_missing_source(
    minimal_safe_env,
):
    """
    GIVEN a missing source path
    WHEN file_move is called
    THEN a FILE_NOT_FOUND SegActionError is raised
    """
    params = FileMoveParams(
        source_path="tmp/missing.bin",
        destination_path="tmp/dest.bin",
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == FILE_NOT_FOUND.code


@pytest.mark.asyncio
async def test_file_move_rejects_destination_directory(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a valid source file
    AND destination path that points to an existing directory
    WHEN file_move is called
    THEN a CONFLICT SegActionError is raised
    """
    source = sandbox_file_factory(
        name="source.bin",
        content=b"source",
    )

    destination_dir_abs = source.abs_path.parent / "existing_dir"
    destination_dir_abs.mkdir()
    destination_dir_rel = source.rel_path.parent / destination_dir_abs.name

    params = FileMoveParams(
        source_path=str(source.rel_path),
        destination_path=str(destination_dir_rel),
        overwrite=False,
    )

    with pytest.raises(SegActionError) as exc:
        await file_move(params)

    assert exc.value.code == CONFLICT.code
