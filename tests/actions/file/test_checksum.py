"""
Unit tests for the checksum_file action.

These tests freeze filesystem, sandboxing, and checksum invariants:
- only sandboxed files are readable
- supported algorithms produce deterministic results
- invalid paths and algorithms are rejected safely
- error mapping is stable and explicit
"""

from __future__ import annotations

import pytest

from seg.actions.dispatcher import SegActionError
from seg.actions.file.checksum import checksum_file
from seg.actions.file.schemas import ChecksumParams

# ============================================================================
# Test constants (frozen contract)
# ============================================================================

TEST_FILE_CONTENT = b"This is a test file\n"

SHA256_EXPECTED = "c87e2ca771bab6024c269b933389d2a92d4941c848c52f155b9b84e1f109fe35"
SHA1_EXPECTED = "b56df8ed5365fca1419818aa384ba3b5e7756047"
MD5_EXPECTED = "5dd39cab1c53c2c77cd352983f9641e1"


# ============================================================================
# Successful checksum computation
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "algorithm, expected_checksum",
    [
        ("sha256", SHA256_EXPECTED),
        ("sha1", SHA1_EXPECTED),
        ("md5", MD5_EXPECTED),
    ],
)
async def test_checksum_file_supported_algorithms(
    sandbox_file_factory, minimal_safe_env, algorithm, expected_checksum
):
    """
    GIVEN a file inside an allowed sandbox subdirectory
    WHEN checksum_file is called with a supported algorithm
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

    result = await checksum_file(params)

    assert result.algorithm == algorithm
    assert result.checksum == expected_checksum
    assert result.size_bytes == len(TEST_FILE_CONTENT)


# ============================================================================
# Path and sandbox enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_checksum_file_rejects_nonexistent_file(
    minimal_safe_env,
):
    """
    GIVEN a valid sandbox path that does not exist
    WHEN checksum_file is called
    THEN a FILE_NOT_FOUND SegActionError is raised
    """
    params = ChecksumParams(
        path="tmp/does_not_exist.bin",
        algorithm="sha256",
    )

    with pytest.raises(SegActionError) as exc:
        await checksum_file(params)

    assert exc.value.code == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_checksum_file_rejects_path_traversal(
    minimal_safe_env,
):
    """
    GIVEN a path attempting directory traversal
    WHEN checksum_file is called
    THEN a PATH_NOT_ALLOWED SegActionError is raised
    """
    params = ChecksumParams(
        path="../outside.bin",
        algorithm="sha256",
    )

    with pytest.raises(SegActionError) as exc:
        await checksum_file(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_checksum_file_rejects_symlink(sandbox_file_factory, minimal_safe_env):
    """
    GIVEN a symlink inside an allowed sandbox subdirectory
    WHEN checksum_file is called
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
        await checksum_file(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


# ============================================================================
# Algorithm validation
# ============================================================================


@pytest.mark.asyncio
async def test_checksum_file_rejects_invalid_algorithm(
    sandbox_file_factory, minimal_safe_env
):
    """
    GIVEN a valid file inside the sandbox
    WHEN checksum_file is called with an unsupported algorithm
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
        await checksum_file(params)

    assert exc.value.code == "INVALID_ALGORITHM"
