"""Route-level handlers and wrappers for SEG file endpoints.

This module keeps route-adjacent orchestration logic used by `seg.routes.files`,
including request parsing wrappers and upload ingestion handlers.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Form, UploadFile
from pydantic import ValidationError

from seg.actions.file.schemas import VerifyChecksumParams
from seg.core.config import Settings, get_settings
from seg.core.errors import (
    FILE_EXTENSION_MISSING,
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    INVALID_ALGORITHM,
    INVALID_REQUEST,
    MIME_MAPPING_NOT_DEFINED,
    UNSUPPORTED_MEDIA_TYPE,
    SegError,
)
from seg.core.schemas.files import DeleteFileResult, FileMetadata, UploadFileRequest
from seg.core.utils.file_storage import (
    FileExtensionMissingError,
    MimeMappingNotDefinedError,
    UnsupportedMediaTypeValidationError,
    _detect_mime,
    _validate_extension_and_mime,
    delete_blob_file,
    delete_metadata_file,
    get_blob_path,
    get_meta_path,
    get_tmp_dir,
    load_file_metadata,
    logger,
    sanitize_download_filename,
    save_file_metadata,
)

# ============================================================================
# Helper classes and functions
# ============================================================================


@dataclass(slots=True, frozen=True)
class FileContentDescriptor:
    """Transport-neutral descriptor for streamed file content."""

    file_id: uuid.UUID
    blob_path: Path
    mime_type: str
    filename: str
    size_bytes: int | None


def safe_load_metadata(
    file_id: uuid.UUID,
    settings: Settings | None = None,
) -> FileMetadata:
    """Safely load and validate file metadata from SEG storage.

    This helper centralizes the metadata loading and validation pipeline used
    across multiple file handlers (e.g., delete, content, metadata retrieval).

    It enforces a consistent error mapping strategy aligned with SEG's
    structured error model (`SegError`), ensuring that:

    - Missing metadata is mapped to FILE_NOT_FOUND
    - Corrupted JSON is mapped to INVALID_REQUEST
    - Schema validation failures are mapped to INVALID_REQUEST
    - Unexpected system errors are mapped to INTERNAL_ERROR

    This function should be used by all handlers that require metadata access
    to avoid duplication and ensure consistent behavior.

    Args:
        file_id: UUID of the file whose metadata should be loaded.
        settings: Optional pre-loaded runtime settings.

    Returns:
        A validated FileMetadata instance.

    Raises:
        SegError:
            - FILE_NOT_FOUND: If metadata file does not exist.
            - INVALID_REQUEST: If metadata is corrupted or invalid.
            - INTERNAL_ERROR: If an unexpected system error occurs.
    """

    cfg = settings or get_settings()

    try:
        metadata = load_file_metadata(file_id, cfg)

    except OSError as exc:
        logger.exception(
            "file.metadata.prepare_failed",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to read file metadata.",
        ) from exc

    except json.JSONDecodeError as exc:
        logger.warning(
            "file.metadata.invalid_json",
            extra={"file_id": str(file_id), "reason": "invalid_json"},
        )
        raise SegError(
            INVALID_REQUEST,
            "Invalid file metadata (corrupted JSON).",
            details={"file_id": str(file_id)},
        ) from exc

    except ValidationError as exc:
        logger.warning(
            "file.metadata.invalid_schema",
            extra={"file_id": str(file_id), "reason": "invalid_schema"},
        )
        raise SegError(
            INVALID_REQUEST,
            "Invalid file metadata schema.",
            details={"file_id": str(file_id)},
        ) from exc

    except Exception as exc:
        logger.exception(
            "file.metadata.prepare_failed",
            extra={"file_id": str(file_id), "reason": "unexpected_error"},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Unexpected error while loading file metadata.",
        ) from exc

    if metadata is None:
        logger.warning(
            "file.metadata.not_found",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    return metadata


# ============================================================================
# DELETE /v1/files/{file_id} handler
# ============================================================================


async def delete_file_handler(
    file_id: uuid.UUID,
    settings: Settings | None = None,
) -> DeleteFileResult:
    """Delete a previously uploaded file and its metadata.

    Flow:
    - Load and validate metadata
    - Verify storage consistency and blob presence
    - Delete blob first, then metadata
    - Return typed delete result
    """

    cfg = settings or get_settings()
    metadata = safe_load_metadata(file_id, cfg)

    if metadata is None:
        logger.warning(
            "file.delete.metadata_not_found",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    if metadata.id != file_id:
        logger.warning(
            "file.delete.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "File metadata does not match requested file id.",
            details={"file_id": str(file_id)},
        )

    if metadata.status != "ready":
        logger.warning(
            "file.delete.not_ready",
            extra={"file_id": str(file_id), "status": metadata.status},
        )
        raise SegError(
            INVALID_REQUEST,
            "File is not in deletable state.",
            details={"file_id": str(file_id), "status": metadata.status},
        )

    if not metadata.stored_filename or not metadata.stored_filename.strip():
        logger.warning(
            "file.delete.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file reference is missing from metadata.",
            details={"file_id": str(file_id)},
        )

    blob_path = get_blob_path(file_id, cfg)
    meta_path = get_meta_path(file_id, cfg)

    if metadata.stored_filename != blob_path.name:
        logger.warning(
            "file.delete.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file reference does not match expected blob path.",
            details={"file_id": str(file_id)},
        )

    if not blob_path.exists():
        logger.warning(
            "file.delete.blob_not_found",
            extra={"file_id": str(file_id), "blob_path": str(blob_path)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    if not blob_path.is_file():
        logger.warning(
            "file.delete.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file path is not a regular file.",
            details={"file_id": str(file_id)},
        )

    try:
        delete_blob_file(file_id, cfg)
    except FileNotFoundError as exc:
        logger.warning(
            "file.delete.blob_not_found",
            extra={"file_id": str(file_id), "blob_path": str(blob_path)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        ) from exc
    except OSError as exc:
        logger.exception(
            "file.delete.blob_delete_failed",
            extra={"file_id": str(file_id), "blob_path": str(blob_path)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to delete file blob.",
        ) from exc

    try:
        delete_metadata_file(file_id, cfg)
    except FileNotFoundError as exc:
        logger.exception(
            "file.delete.metadata_delete_failed",
            extra={"file_id": str(file_id), "meta_path": str(meta_path)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to delete file metadata.",
        ) from exc
    except OSError as exc:
        logger.exception(
            "file.delete.metadata_delete_failed",
            extra={"file_id": str(file_id), "meta_path": str(meta_path)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to delete file metadata.",
        ) from exc

    logger.info(
        "file.delete.succeeded",
        extra={
            "file_id": str(file_id),
            "blob_path": str(blob_path),
            "meta_path": str(meta_path),
            "original_filename": metadata.original_filename,
            "stored_filename": metadata.stored_filename,
            "mime_type": metadata.mime_type,
            "size_bytes": metadata.size_bytes,
        },
    )

    return DeleteFileResult(id=file_id, deleted=True)


def parse_post_file_request(
    checksum: Annotated[str | None, Form()] = None,
) -> UploadFileRequest:
    """Build the typed request schema for `POST /v1/files` form fields."""

    return UploadFileRequest(checksum=checksum)


# ============================================================================
# GET /v1/files/{file_id} handler
# ============================================================================


async def get_file_metadata_handler(
    file_id: uuid.UUID,
    settings: Settings | None = None,
) -> FileMetadata:
    """Load metadata for a previously uploaded file.

    This handler orchestrates storage access and maps low-level errors into
    SEG's standardized error model.

    Error mapping:
    - FILE_NOT_FOUND → metadata file does not exist
    - INVALID_REQUEST → metadata exists but is invalid/corrupted
    - INTERNAL_ERROR → unexpected system or IO failure
    """

    cfg = settings or get_settings()
    metadata = safe_load_metadata(file_id, cfg)

    logger.info(
        "file.metadata.retrieved",
        extra={"file_id": str(file_id)},
    )

    return metadata


# ============================================================================
# GET /v1/files/{file_id}/content handler
# ============================================================================


async def get_file_content_handler(
    file_id: uuid.UUID,
    settings: Settings | None = None,
) -> FileContentDescriptor:
    """Resolve and validate metadata + blob path for content streaming."""

    cfg = settings or get_settings()
    metadata = safe_load_metadata(file_id, cfg)

    if metadata is None:
        logger.warning(
            "file.content.metadata_not_found",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    if metadata.id != file_id:
        logger.warning(
            "file.content.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "File metadata does not match requested file id.",
            details={"file_id": str(file_id)},
        )

    if metadata.status != "ready":
        logger.warning(
            "file.content.not_ready",
            extra={"file_id": str(file_id), "status": metadata.status},
        )
        raise SegError(
            INVALID_REQUEST,
            "File is not available for download.",
            details={"file_id": str(file_id), "status": metadata.status},
        )

    if not metadata.stored_filename or not metadata.stored_filename.strip():
        logger.warning(
            "file.content.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file reference is missing from metadata.",
            details={"file_id": str(file_id)},
        )

    blob_path = get_blob_path(file_id, cfg)

    if metadata.stored_filename != blob_path.name:
        logger.warning(
            "file.content.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file reference does not match expected blob path.",
            details={"file_id": str(file_id)},
        )

    if not blob_path.exists():
        logger.warning(
            "file.content.blob_not_found",
            extra={"file_id": str(file_id), "blob_path": str(blob_path)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    if not blob_path.is_file():
        logger.warning(
            "file.content.invalid_metadata",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Stored file path is not a regular file.",
            details={"file_id": str(file_id)},
        )

    try:
        size_bytes = blob_path.stat().st_size
    except OSError as exc:
        logger.exception(
            "file.content.prepare_failed",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to prepare file content for streaming.",
        ) from exc

    mime_type = metadata.mime_type.strip().lower() if metadata.mime_type else ""
    if "/" not in mime_type:
        mime_type = "application/octet-stream"

    filename = sanitize_download_filename(
        metadata.original_filename,
        file_id,
    )

    logger.info(
        "file.content.resolved",
        extra={
            "file_id": str(file_id),
            "blob_path": str(blob_path),
            "mime_type": mime_type,
            "filename": filename,
            "size_bytes": size_bytes,
        },
    )

    return FileContentDescriptor(
        file_id=file_id,
        blob_path=blob_path,
        mime_type=mime_type,
        filename=filename,
        size_bytes=size_bytes,
    )


# ============================================================================
# POST /v1/files handler
# ============================================================================


async def upload_file_handler(
    upload: UploadFile,
    verify_checksum: VerifyChecksumParams | None = None,
    settings: Settings | None = None,
) -> FileMetadata:
    """Validate and persist an uploaded file under SEG-managed storage.

    Args:
        upload: Incoming FastAPI multipart file stream.
        verify_checksum: Optional checksum constraint provided by the client.
        settings: Optional pre-loaded runtime settings.

    Returns:
        Persisted file metadata.

    Raises:
        SegError: If validation or persistence fails.
    """

    cfg = settings or get_settings()
    file_id = uuid.uuid4()
    tmp_path = get_tmp_dir(cfg) / f"upload_{file_id}.tmp"
    blob_path = get_blob_path(file_id, cfg)

    hasher = hashlib.sha256()
    size_bytes = 0
    max_bytes = cfg.seg_max_bytes
    moved_to_blob = False

    try:
        # Note: UploadFile stream is consumed during read; cannot be reused.
        with tmp_path.open("wb") as temp_f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break

                size_bytes += len(chunk)
                if max_bytes is not None and size_bytes > max_bytes:
                    raise SegError(FILE_TOO_LARGE)

                hasher.update(chunk)
                temp_f.write(chunk)

            if size_bytes == 0:
                raise SegError(INVALID_REQUEST, "Empty file is not allowed.")

        sha256 = hasher.hexdigest()

        if verify_checksum is not None:
            if verify_checksum.algorithm != "sha256":
                raise SegError(INVALID_ALGORITHM)
            if sha256.lower() != verify_checksum.expected.strip().lower():
                raise SegError(
                    INVALID_REQUEST,
                    "Checksum mismatch.",
                    details={
                        "algorithm": "sha256",
                        "expected": verify_checksum.expected,
                        "actual": sha256,
                    },
                )

        detected_mime = _detect_mime(tmp_path)
        original_filename = Path(upload.filename or "uploaded_file").name
        try:
            extension = _validate_extension_and_mime(original_filename, detected_mime)
        except FileExtensionMissingError as exc:
            raise SegError(FILE_EXTENSION_MISSING) from exc
        except MimeMappingNotDefinedError as exc:
            raise SegError(
                MIME_MAPPING_NOT_DEFINED,
                details={"extension": exc.extension},
            ) from exc
        except UnsupportedMediaTypeValidationError as exc:
            raise SegError(
                UNSUPPORTED_MEDIA_TYPE,
                message=str(exc),
                details={
                    "extension": exc.extension,
                    "detected_mime": exc.detected_mime,
                },
            ) from exc

        os.replace(tmp_path, blob_path)
        moved_to_blob = True

        now_utc = datetime.now(UTC)
        metadata = FileMetadata(
            id=file_id,
            original_filename=original_filename,
            stored_filename=blob_path.name,
            mime_type=detected_mime,
            extension=extension,
            size_bytes=size_bytes,
            sha256=sha256,
            created_at=now_utc,
            updated_at=now_utc,
            status="ready",
        )

        try:
            save_file_metadata(metadata, cfg)
        except Exception as exc:
            if moved_to_blob and blob_path.exists():
                try:
                    blob_path.unlink()
                except OSError:
                    logger.exception(
                        "Failed to cleanup blob after metadata write error"
                    )
            raise SegError(
                INTERNAL_ERROR,
                "Failed to persist file metadata.",
            ) from exc

        logger.info(
            "File stored",
            extra={
                "file_id": str(file_id),
                "size": size_bytes,
                "mime": detected_mime,
                "original_filename": original_filename,
            },
        )

        return metadata

    except SegError:
        raise
    except Exception as exc:
        raise SegError(INTERNAL_ERROR) from exc
    finally:
        try:
            await upload.close()
        except Exception:
            logger.exception("Failed to close uploaded file stream")

        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                logger.exception("Failed to cleanup temporary upload file")
