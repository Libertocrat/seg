"""GET /v1/files/{file_id}/content route handler."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from seg.core.config import Settings, get_settings
from seg.core.errors import FILE_NOT_FOUND, INTERNAL_ERROR, INVALID_REQUEST, SegError
from seg.core.utils.file_storage import (
    get_blob_path,
    logger,
    sanitize_download_filename,
)
from seg.routes.files.utils import safe_load_metadata


@dataclass(slots=True, frozen=True)
class FileContentDescriptor:
    """Transport-neutral descriptor for streamed file content."""

    file_id: uuid.UUID
    blob_path: Path
    mime_type: str
    filename: str
    size_bytes: int | None


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
