"""SEG-managed local file storage helpers and upload workflow.

This module implements the upload persistence flow used by `POST /v1/files`,
including temporary staging, validation, atomic blob promotion, and metadata
JSON persistence.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator
from uuid import UUID

import magic

from seg.core.config import Settings, get_settings
from seg.core.schemas.files import FileMetadata
from seg.core.security.mime_map import EXTENSION_MIME_MAP

logger = logging.getLogger("seg.core.file_storage")
_MAGIC = magic.Magic(mime=True)

_DISALLOWED_EXECUTABLE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".dll",
        ".ps1",
        ".sh",
    }
)

_DISALLOWED_EXECUTABLE_MIME_PREFIXES = ("application/x-dosexec",)

_DISALLOWED_EXECUTABLE_MIME_EXACT = frozenset(
    {
        "application/vnd.microsoft.portable-executable",
        "application/x-msdownload",
        "application/x-shellscript",
        "text/x-shellscript",
    }
)


class FileExtensionMissingError(ValueError):
    """Raised when an uploaded filename has no extension."""


class MimeMappingNotDefinedError(ValueError):
    """Raised when SEG has no MIME mapping for the file extension."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"No MIME mapping defined for extension: {extension}")


class UnsupportedMediaTypeValidationError(ValueError):
    """Raised when uploaded extension and detected MIME are incompatible."""

    def __init__(self, extension: str, detected_mime: str, message: str):
        self.extension = extension
        self.detected_mime = detected_mime
        super().__init__(message)


def get_data_root(settings: Settings | None = None) -> Path:
    """Return the configured SEG data root as an absolute expanded path.

    Args:
        settings: Optional pre-loaded runtime settings.

    Returns:
        Absolute expanded path to the configured data root.
    """

    cfg = settings or get_settings()
    return Path(cfg.seg_data_root).expanduser().resolve()


def get_files_root(settings: Settings | None = None) -> Path:
    """Return the root directory for file storage.

    Args:
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path for the `files/` storage root under SEG data root.
    """

    return get_data_root(settings) / "files"


def get_blob_dir(settings: Settings | None = None) -> Path:
    """Return the directory where validated blobs are persisted.

    Args:
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path to the `files/blobs/` directory.
    """

    return get_files_root(settings) / "blobs"


def get_meta_dir(settings: Settings | None = None) -> Path:
    """Return the directory where metadata JSON files are persisted.

    Args:
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path to the `files/meta/` directory.
    """

    return get_files_root(settings) / "meta"


def get_tmp_dir(settings: Settings | None = None) -> Path:
    """Return the directory where temporary uploads are staged.

    Args:
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path to the `files/tmp/` directory.
    """

    return get_files_root(settings) / "tmp"


def get_blob_path(file_id: UUID, settings: Settings | None = None) -> Path:
    """Return the persisted blob path for a file id.

    Args:
        file_id: UUID of the persisted file.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path to `files/blobs/file_<uuid>.bin`.
    """

    return get_blob_dir(settings) / f"file_{file_id}.bin"


def get_meta_path(file_id: UUID, settings: Settings | None = None) -> Path:
    """Return the persisted metadata JSON path for a file id.

    Args:
        file_id: UUID of the persisted file.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Path to `files/meta/file_<uuid>.json`.
    """

    return get_meta_dir(settings) / f"file_{file_id}.json"


def ensure_storage_dirs(settings: Settings | None = None) -> None:
    """Create SEG storage directories with idempotent behavior.

    Args:
        settings: Optional pre-loaded runtime settings.
    """

    data_root = get_data_root(settings)
    data_root.mkdir(parents=True, exist_ok=True)
    get_blob_dir(settings).mkdir(parents=True, exist_ok=True)
    get_meta_dir(settings).mkdir(parents=True, exist_ok=True)
    get_tmp_dir(settings).mkdir(parents=True, exist_ok=True)


def save_file_metadata(
    metadata: FileMetadata,
    settings: Settings | None = None,
) -> None:
    """Persist typed file metadata to JSON using an atomic replace.

    Args:
        metadata: Metadata model to persist.
        settings: Optional pre-loaded runtime settings.
    """

    meta_path = get_meta_path(metadata.id, settings)
    tmp_meta_path = meta_path.with_suffix(".json.tmp")
    payload = metadata.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    tmp_meta_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_meta_path, meta_path)


def load_file_metadata(
    file_id: UUID,
    settings: Settings | None = None,
) -> FileMetadata | None:
    """Load typed file metadata JSON for the given file id.

    Args:
        file_id: UUID of the persisted file.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Parsed and validated file metadata model, or None if not found.

    Raises:
        OSError: If file cannot be read.
        json.JSONDecodeError: If metadata is invalid JSON.
        ValidationError: If schema validation fails.
    """

    meta_path = get_meta_path(file_id, settings)

    if not meta_path.exists():
        return None

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    return FileMetadata.model_validate(payload)


def delete_blob_file(
    file_id: UUID,
    settings: Settings | None = None,
) -> Path:
    """Delete the persisted blob file for a file id.

    This operation is strict and never silent:
    - Raises FileNotFoundError if the blob does not exist
    - Raises OSError on failure

    Args:
        file_id: UUID of the persisted file.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Deleted blob file path.

    Raises:
        FileNotFoundError: If the blob file does not exist.
        OSError: If deletion fails due to OS-level error.
    """

    blob_path = get_blob_path(file_id, settings)
    blob_path.unlink()
    return blob_path


def delete_metadata_file(
    file_id: UUID,
    settings: Settings | None = None,
) -> Path:
    """Delete the persisted metadata file for a file id.

    This operation is strict and never silent:
    - Raises FileNotFoundError if metadata does not exist
    - Raises OSError on failure

    Args:
        file_id: UUID of the persisted file.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Deleted metadata file path.

    Raises:
        FileNotFoundError: If the metadata file does not exist.
        OSError: If deletion fails due to OS-level error.
    """

    meta_path = get_meta_path(file_id, settings)
    meta_path.unlink()
    return meta_path


def sanitize_download_filename(
    original_filename: str | None,
    file_id: UUID,
) -> str:
    """Return a safe filename for Content-Disposition download responses.

    Args:
        original_filename: Filename persisted in metadata.
        file_id: UUID used for deterministic fallback naming.

    Returns:
        Sanitized filename, or `file_<uuid>.bin` fallback.
    """

    fallback = f"file_{file_id}.bin"
    candidate = Path(original_filename or "").name

    if not candidate:
        return fallback

    sanitized = "".join(ch for ch in candidate if ch >= " " and ch != "\x7f")
    sanitized = sanitized.replace("/", "").replace("\\", "").strip().strip(".")

    return sanitized or fallback


def iter_file_chunks(
    path: Path,
    chunk_size: int = 65536,
) -> Iterator[bytes]:
    """Yield file bytes in fixed-size chunks.

    Args:
        path: File path to stream.
        chunk_size: Bytes per chunk.

    Yields:
        Binary chunks until EOF.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    with path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _normalize_extension(filename: str | None) -> str:
    """Normalize a filename extension to lowercase with leading dot.

    Args:
        filename: Input filename or `None`.

    Returns:
        Normalized extension (e.g. `.pdf`) or an empty string.
    """

    if not filename:
        return ""
    return Path(filename).suffix.strip().lower()


def _detect_mime(path: Path) -> str:
    """Detect MIME type from file contents.

    Args:
        path: Path of the staged file.

    Returns:
        Lowercased content-based MIME type.
    """

    with path.open("rb") as f:
        sample = f.read(8192)
    return _MAGIC.from_buffer(sample).strip().lower()


def _is_disallowed_executable(extension: str, mime_type: str) -> bool:
    """Return whether a file should be rejected as executable content.

    Args:
        extension: Normalized file extension.
        mime_type: Content-based detected MIME type.

    Returns:
        True if file type is considered executable and disallowed.
    """

    if extension in _DISALLOWED_EXECUTABLE_EXTENSIONS:
        return True
    if mime_type in _DISALLOWED_EXECUTABLE_MIME_EXACT:
        return True
    return mime_type.startswith(_DISALLOWED_EXECUTABLE_MIME_PREFIXES)


def _validate_extension_and_mime(original_filename: str, mime_type: str) -> str:
    """Validate extension and MIME compatibility against trusted mapping.

    Args:
        original_filename: Normalized basename from client upload.
        mime_type: Content-based MIME detected by SEG.

    Returns:
        Normalized extension when validation succeeds.

    Raises:
        FileExtensionMissingError: If extension is missing.
        MimeMappingNotDefinedError: If extension is unknown by policy mapping.
        UnsupportedMediaTypeValidationError: If extension and detected MIME mismatch.
    """

    extension = _normalize_extension(original_filename)
    if not extension:
        raise FileExtensionMissingError()

    allowed_mimes = EXTENSION_MIME_MAP.get(extension)
    if not allowed_mimes:
        raise MimeMappingNotDefinedError(
            extension=extension,
        )

    if mime_type not in {m.lower() for m in allowed_mimes}:
        raise UnsupportedMediaTypeValidationError(
            extension=extension,
            detected_mime=mime_type,
            message="Uploaded file extension does not match detected MIME type.",
        )

    if _is_disallowed_executable(extension, mime_type):
        raise UnsupportedMediaTypeValidationError(
            extension=extension,
            detected_mime=mime_type,
            message="Executable file types are not allowed.",
        )

    return extension
