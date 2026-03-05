"""
Unit tests for the file_checksum action.

These tests freeze filesystem, sandboxing, and checksum invariants:
- only sandboxed files are readable
- supported algorithms produce deterministic results
- invalid paths and algorithms are rejected safely
- error mapping is stable and explicit
"""

from __future__ import annotations

import pytest

from seg.actions.exceptions import SegActionError
from seg.actions.file.checksum import file_checksum
from seg.actions.file.schemas import ChecksumParams
from seg.core.errors import FILE_NOT_FOUND, INVALID_ALGORITHM, PATH_NOT_ALLOWED

# ============================================================================
# Test Constants
# ============================================================================

TEST_FILE_CONTENT = b"This is a test file\n"

SHA256_EXPECTED = "c87e2ca771bab6024c269b933389d2a92d4941c848c52f155b9b84e1f109fe35"
SHA1_EXPECTED = "b56df8ed5365fca1419818aa384ba3b5e7756047"
MD5_EXPECTED = "5dd39cab1c53c2c77cd352983f9641e1"


# ============================================================================
# Successful Checksum Computation
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "algorithm, expected_checksum",
    [
        ("sha256", SHA256_EXPECTED),
        ("sha1", SHA1_EXPECTED),
        ("md5", MD5_EXPECTED),
    ],
    ids=[
        "sha256",
        "sha1",
        "md5",
    ],
)
async def test_file_checksum_supported_algorithms(
    sandbox_file_factory, minimal_safe_env, algorithm, expected_checksum
):
    """
    GIVEN a file inside an allowed sandbox subdirectory
    WHEN file_checksum is called with a supported algorithm
    THEN the correct checksum and file size are returned
    """
    sf = sandbox_file_factory(
        name="test_file.bin",
        content=TEST_FILE_CONTENT,
    )

    params = ChecksumParams(
        path=str(sf.rel_path),
        algorithm=algorithm,
    )

    result = await file_checksum(params)

    assert result.algorithm == algorithm
    assert result.checksum == expected_checksum
    assert result.size_bytes == len(TEST_FILE_CONTENT)


# ============================================================================
# Path and Sandbox Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_checksum_rejects_nonexistent_file(
    minimal_safe_env,
):
    """
    GIVEN a valid sandbox path that does not exist
    WHEN file_checksum is called
    THEN a FILE_NOT_FOUND SegActionError is raised
    """
    params = ChecksumParams(
        path="tmp/does_not_exist.bin",
        algorithm="sha256",
    )

    with pytest.raises(SegActionError) as exc:
        await file_checksum(params)

    assert exc.value.code == FILE_NOT_FOUND.code


@pytest.mark.asyncio
async def test_file_checksum_rejects_path_traversal(
    minimal_safe_env,
):
    """
    GIVEN a path attempting directory traversal
    WHEN file_checksum is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    params = ChecksumParams(
        path="../outside.bin",
        algorithm="sha256",
    )

    with pytest.raises(SegActionError) as exc:
        await file_checksum(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


@pytest.mark.asyncio
async def test_file_checksum_rejects_symlink(sandbox_file_factory, minimal_safe_env):
    """
    GIVEN a symlink inside an allowed sandbox subdirectory
    WHEN file_checksum is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    target = sandbox_file_factory(
        name="target.bin",
        content=TEST_FILE_CONTENT,
    )
    symlink = target.abs_path.parent / "link.bin"
    symlink.symlink_to(target.abs_path)

    relative_path = str(target.rel_path.parent / symlink.name)

    params = ChecksumParams(
        path=relative_path,
        algorithm="sha256",
    )

    with pytest.raises(SegActionError) as exc:
        await file_checksum(params)

    assert exc.value.code == PATH_NOT_ALLOWED.code


# ============================================================================
# Algorithm validation
# ============================================================================


@pytest.mark.asyncio
async def test_file_checksum_rejects_invalid_algorithm(
    sandbox_file_factory, minimal_safe_env
):
    """
    GIVEN a valid file inside the sandbox
    WHEN file_checksum is called with an unsupported algorithm
    THEN an INVALID_ALGORITHM SegActionError is raised
    """
    file = sandbox_file_factory(
        name="test_file.bin",
        content=TEST_FILE_CONTENT,
    )

    # Intentionally bypass Pydantic Literal validation to exercise
    # action-level algorithm handling.
    params = ChecksumParams.model_construct(
        path=str(file.rel_path),
        algorithm="not-a-real-algo",
    )

    with pytest.raises(SegActionError) as exc:
        await file_checksum(params)

    assert exc.value.code == INVALID_ALGORITHM.code
