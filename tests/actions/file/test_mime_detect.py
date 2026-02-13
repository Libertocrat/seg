"""
Unit tests for the file_mime_detect action.

These tests verify:
- correct MIME detection for representative file types
- sandbox enforcement
- symlink rejection
- file size limits
- stable error mapping
"""

from __future__ import annotations

import pytest

from seg.actions.dispatcher import SegActionError
from seg.actions.file.mime_detect import file_mime_detect
from seg.actions.file.schemas import MimeDetectParams

# ============================================================================
# Successful MIME detection
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_type, filename, expected_keywords",
    [
        pytest.param("text", "file.txt", ("text",), id="text_plain"),
        pytest.param("markdown", "doc.md", ("text",), id="markdown"),
        pytest.param("csv", "data.csv", ("csv", "text"), id="csv"),
        pytest.param("png", "image.png", ("png",), id="png_image"),
        pytest.param("pdf", "doc.pdf", ("pdf",), id="pdf_document"),
        pytest.param("zip", "archive.zip", ("zip",), id="zip_archive"),
        pytest.param("tar", "archive.tar", ("tar",), id="tar_archive"),
        pytest.param("gzip", "archive.gz", ("gzip",), id="gzip_archive"),
        pytest.param(
            "exe", "program.exe", ("exe", "dos", "msdownload"), id="windows_exe"
        ),
        pytest.param(
            "elf", "program.bin", ("elf", "executable", "pie"), id="linux_elf"
        ),
        pytest.param("shell", "script.sh", ("shell", "text"), id="shell_script"),
        pytest.param("python", "script.py", ("python", "text"), id="python_script"),
        pytest.param(
            "javascript", "script.js", ("javascript", "text"), id="javascript_script"
        ),
    ],
)
async def test_file_mime_detect_success(
    file_factory,
    minimal_safe_env,
    file_type,
    filename,
    expected_keywords,
):
    """
    GIVEN a structurally valid file inside the sandbox
    WHEN file_mime_detect is executed
    THEN the correct MIME type is returned
    """
    sf = file_factory(file_type, filename)

    params = MimeDetectParams(path=str(sf.rel_path))

    result = await file_mime_detect(params)

    mime = result.mime.lower()
    print(f"Detected MIME for {file_type}: {mime}")

    assert any(
        keyword in mime for keyword in expected_keywords
    ), f"Unexpected MIME '{result.mime}' for file_type='{file_type}'"


@pytest.mark.asyncio
async def test_file_mime_detect_unknown_binary(
    sandbox_file_factory,
    minimal_safe_env,
):
    """
    GIVEN a binary file with no known signature
    WHEN file_mime_detect is called
    THEN application/octet-stream is returned
    """
    sf = sandbox_file_factory(
        name="random.bin",
        content=b"\x00" * 1024,
    )

    params = MimeDetectParams(path=str(sf.rel_path))

    result = await file_mime_detect(params)

    assert result.mime.startswith("application/octet-stream")


# ============================================================================
# Security enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_mime_detect_rejects_nonexistent_file(minimal_safe_env):
    """
    GIVEN a valid sandbox-relative path that does not exist
    WHEN file_mime_detect is called
    THEN FILE_NOT_FOUND is raised
    """
    params = MimeDetectParams(path="tmp/missing.bin")

    with pytest.raises(SegActionError) as exc:
        await file_mime_detect(params)

    assert exc.value.code == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_file_mime_detect_rejects_path_traversal(minimal_safe_env):
    """
    GIVEN a path attempting directory traversal
    WHEN file_mime_detect is called
    THEN PATH_NOT_ALLOWED is raised
    """
    params = MimeDetectParams(path="../outside.bin")

    with pytest.raises(SegActionError) as exc:
        await file_mime_detect(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_file_mime_detect_rejects_symlink(file_factory, minimal_safe_env):
    """
    GIVEN a symlink inside the sandbox
    WHEN file_mime_detect is called
    THEN PATH_NOT_ALLOWED is raised
    """
    target = file_factory("text", "target.txt")
    symlink = target.abs_path.parent / "link.txt"
    symlink.symlink_to(target.abs_path)

    relative = str(target.rel_path.parent / symlink.name)

    params = MimeDetectParams(path=relative)

    with pytest.raises(SegActionError) as exc:
        await file_mime_detect(params)

    assert exc.value.code == "PATH_NOT_ALLOWED"


# ============================================================================
# Size enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_file_mime_detect_rejects_file_too_large(
    sandbox_file_factory,
    minimal_safe_env,
    monkeypatch,
):
    """
    GIVEN a file exceeding SEG_MAX_BYTES
    WHEN file_mime_detect is called
    THEN FILE_TOO_LARGE is raised
    """
    monkeypatch.setenv("SEG_MAX_BYTES", "10")

    sf = sandbox_file_factory(
        name="big.bin",
        content=b"x" * 100,
    )

    params = MimeDetectParams(path=str(sf.rel_path))

    with pytest.raises(SegActionError) as exc:
        await file_mime_detect(params)

    assert exc.value.code == "FILE_TOO_LARGE"
