"""
Unit tests for the file_verify action.

These tests verify:
- policy-report behavior (no exception on policy failure)
- MIME ↔ extension coherence
- allowed extension / MIME policies
- optional checksum validation
- new policy error codes:
    - FILE_EXTENSION_MISSING
    - MIME_MAPPING_NOT_DEFINED
"""

from __future__ import annotations

import hashlib

import pytest

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import FileVerifyParams, VerifyChecksumParams
from seg.actions.file.verify import file_verify
from seg.core.errors import (
    FILE_EXTENSION_MISSING,
    FILE_NOT_FOUND,
    MIME_MAPPING_NOT_DEFINED,
)
from seg.core.security.mime_map import EXTENSION_MIME_MAP

# ============================================================================
# Successful Verification Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_file_verify_success_basic_png(file_factory, minimal_safe_env):
    """
    GIVEN a valid PNG file with matching extension and MIME
    WHEN file_verify is executed without additional constraints
    THEN file_verified is True
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(path=str(sf.rel_path))

    result = await file_verify(params)

    assert result.file_verified is True
    assert result.mime_matches is True
    assert result.extension_allowed is True
    assert result.mime_allowed is True
    assert result.checksum_matches is None
    assert result.size_bytes > 0
    assert result.extension == ".png"
    assert result.detected_mime.startswith("image/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "algorithm",
    ["sha256", "md5", "sha1"],
    ids=["sha256", "md5", "sha1"],
)
@pytest.mark.parametrize(
    "file_type,filename,expected_extension",
    [
        ("text", "file.txt", ".txt"),
        ("md", "doc.md", ".md"),
        ("pdf", "doc.pdf", ".pdf"),
        ("csv", "data.csv", ".csv"),
        ("png", "image.png", ".png"),
        ("zip", "archive.zip", ".zip"),
        ("tar", "archive.tar", ".tar"),
    ],
    ids=["text", "markdown", "pdf", "csv", "png", "zip", "tar"],
)
async def test_file_verify_various_algorithms_and_types(
    file_factory,
    minimal_safe_env,
    algorithm,
    file_type,
    filename,
    expected_extension,
):
    """
    GIVEN files of various types and a checksum algorithm
    WHEN `file_verify` is executed with the corresponding expected digest
    THEN the action validates the checksum and returns all expected result
    fields (`file_verified`, `mime_matches`, `extension`, `extension_allowed`,
    `mime_allowed`, `checksum_matches`, `size_bytes`, `detected_mime`).
    """
    sf = file_factory(file_type, filename)

    content = sf.abs_path.read_bytes()

    if algorithm == "sha256":
        expected = hashlib.sha256(content).hexdigest()
    elif algorithm == "md5":
        expected = hashlib.md5(content).hexdigest()  # noqa: S324
    elif algorithm == "sha1":
        expected = hashlib.sha1(content).hexdigest()  # noqa: S324
    else:
        pytest.skip(f"unsupported algorithm in test matrix: {algorithm}")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        checksum=VerifyChecksumParams(expected=expected, algorithm=algorithm),
    )

    result = await file_verify(params)

    # Checksum-specific assertions
    assert result.checksum_matches is True
    assert result.size_bytes > 0

    # Full happy-path result assertions
    assert result.file_verified is True
    assert result.mime_matches is True
    assert result.extension == expected_extension
    assert result.extension_allowed is True
    assert result.mime_allowed is True
    assert result.detected_mime is not None


# ============================================================================
# Policy-report failures (no exception)
# ============================================================================


@pytest.mark.asyncio
async def test_file_verify_mime_mismatch(file_factory, minimal_safe_env):
    """
    GIVEN a PNG file
    WHEN expected_mime is forced to text/plain
    THEN file_verified is False but no exception is raised
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        expected_mime="text/plain",
    )

    result = await file_verify(params)

    assert result.file_verified is False
    assert result.mime_matches is False


@pytest.mark.asyncio
async def test_file_verify_extension_not_allowed(file_factory, minimal_safe_env):
    """
    GIVEN a PNG file
    WHEN allowed_extensions excludes .png
    THEN file_verified is False
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        allowed_extensions=[".pdf"],
    )

    result = await file_verify(params)

    assert result.file_verified is False
    assert result.extension_allowed is False


@pytest.mark.asyncio
async def test_file_verify_mime_not_allowed(file_factory, minimal_safe_env):
    """
    GIVEN a PNG file
    WHEN allowed_mime_types excludes image/png
    THEN file_verified is False
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        allowed_mime_types=["application/pdf"],
    )

    result = await file_verify(params)

    assert result.file_verified is False
    assert result.mime_allowed is False


@pytest.mark.asyncio
async def test_file_verify_checksum_mismatch(file_factory, minimal_safe_env):
    """
    GIVEN a valid file
    WHEN an incorrect checksum is provided
    THEN file_verified is False
    """
    sf = file_factory("text", "file.txt")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        checksum=VerifyChecksumParams(
            expected="deadbeef",
            algorithm="sha256",
        ),
    )

    result = await file_verify(params)

    assert result.file_verified is False
    assert result.checksum_matches is False


# ============================================================================
# New policy error codes
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Dockerfile", id="dockerfile_no_ext"),
        pytest.param("README", id="readme_no_ext"),
        pytest.param("file.", id="trailing_dot"),
    ],
)
async def test_file_verify_extension_missing(
    minimal_safe_env, sandbox_file_factory, name
):
    """GIVEN files lacking a usable extension

    WHEN `expected_mime` is not provided

    THEN `FILE_EXTENSION_MISSING` is raised.
    """
    sf = sandbox_file_factory(name=name, content=b"FROM python:3.12\n")

    params = FileVerifyParams(path=str(sf.rel_path))

    with pytest.raises(SegActionError) as exc:
        await file_verify(params)

    assert exc.value.code == FILE_EXTENSION_MISSING.code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ext",
    [
        pytest.param(".unknownext", id="unknownext"),
        pytest.param(".xyz", id="xyz"),
        pytest.param(".foo", id="foo"),
    ],
)
async def test_file_verify_mapping_not_defined(
    sandbox_file_factory, minimal_safe_env, ext
):
    """
    GIVEN a file with an extension that has no canonical mapping
    WHEN `expected_mime` is not provided
    THEN `MIME_MAPPING_NOT_DEFINED` is raised and `details.extension` is set.
    """
    name = f"file{ext}"
    sf = sandbox_file_factory(name=name, content=b"random data")

    params = FileVerifyParams(path=str(sf.rel_path))

    with pytest.raises(SegActionError) as exc:
        await file_verify(params)

    assert exc.value.code == MIME_MAPPING_NOT_DEFINED.code
    assert exc.value.details is not None
    assert exc.value.details.get("extension") == ext


# ============================================================================
# Normalization of inputs (e.g. MIME types, extensions) for flexible matching
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_mime",
    [
        pytest.param(" Image/PNG ", id="spaces"),
        pytest.param("IMAGE/PNG", id="upper"),
        pytest.param("image/png", id="lower"),
        pytest.param(" image/PNG", id="mixed_spaces"),
    ],
)
async def test_file_verify_expected_mime_normalization(
    file_factory, minimal_safe_env, expected_mime
):
    """
    GIVEN a PNG file
    WHEN `expected_mime` is provided with varied spacing/casing
    THEN normalization (`strip()` + `lower()`) allows matching the detected
    MIME and `mime_matches` is True.
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(path=str(sf.rel_path), expected_mime=expected_mime)

    result = await file_verify(params)

    assert result.mime_matches is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowed_mime,allowed_ext",
    [
        pytest.param([" Image/PNG "], ["PNG"], id="mime_spaces_ext_no_dot"),
        pytest.param(["image/PNG"], [".PNG"], id="mime_case_ext_dot"),
        pytest.param(
            [" Image/PNG ", "application/pdf"],
            [" pdf ", "PNG"],
            id="multi_values_whitespace",
        ),
    ],
)
async def test_file_verify_allowed_lists_normalization(
    file_factory, minimal_safe_env, allowed_mime, allowed_ext
):
    """
    GIVEN a PNG file
    WHEN `allowed_mime_types` and `allowed_extensions` contain varied spacing/casing
    THEN normalization allows correct matching and both `mime_allowed` and
    `extension_allowed` are True.
    """
    sf = file_factory("png", "image.png")

    params = FileVerifyParams(
        path=str(sf.rel_path),
        allowed_mime_types=allowed_mime,
        allowed_extensions=allowed_ext,
    )

    result = await file_verify(params)

    assert result.mime_allowed is True
    assert result.extension_allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,expected_ext",
    [
        pytest.param("IMAGE.PNG", ".png", id="all_upper"),
        pytest.param("Image.PnG", ".png", id="mixed_case"),
        pytest.param("image.PNG", ".png", id="upper_ext"),
    ],
)
async def test_file_verify_extension_case_insensitive(
    file_factory, minimal_safe_env, filename, expected_ext
):
    """
    GIVEN PNG files with varied extension casing
    WHEN `file_verify` is executed
    THEN the returned `extension` is normalized (lowercase with leading dot)
    and `mime_matches` is True.
    """
    sf = file_factory("png", filename)

    params = FileVerifyParams(path=str(sf.rel_path))

    result = await file_verify(params)

    assert result.extension == expected_ext
    assert result.mime_matches is True


@pytest.mark.asyncio
async def test_file_verify_md_multi_mapping(file_factory, minimal_safe_env):
    """
    GIVEN a Markdown file
    WHEN the extension `.md` maps to multiple MIME types per the canonical
    mapping
    THEN the detected MIME must be one of the allowed values and
    `mime_matches` is True.
    """
    sf = file_factory("text", "doc.md")

    params = FileVerifyParams(path=str(sf.rel_path))

    result = await file_verify(params)

    allowed = {m.lower() for m in EXTENSION_MIME_MAP.get(".md", set())}
    assert result.detected_mime in allowed
    assert result.mime_matches is True


# ============================================================================
# Technical errors (propagated from underlying handlers)
# ============================================================================


@pytest.mark.asyncio
async def test_file_verify_rejects_nonexistent_file(minimal_safe_env):
    """
    GIVEN a non-existent file
    WHEN file_verify is executed
    THEN FILE_NOT_FOUND is raised
    """
    params = FileVerifyParams(path="tmp/missing.bin")

    with pytest.raises(SegActionError) as exc:
        await file_verify(params)

    assert exc.value.code == FILE_NOT_FOUND.code
