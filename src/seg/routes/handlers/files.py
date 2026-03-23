"""Route-level handlers and wrappers for SEG file endpoints.

This module keeps route-adjacent orchestration logic used by `seg.routes.files`,
including request parsing wrappers and upload ingestion handlers.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Form, UploadFile

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
from seg.core.schemas.files import FileMetadata, UploadFileRequest
from seg.core.utils.file_storage import (
    FileExtensionMissingError,
    MimeMappingNotDefinedError,
    UnsupportedMediaTypeValidationError,
    _detect_mime,
    _validate_extension_and_mime,
    get_blob_path,
    get_meta_path,
    get_tmp_dir,
    logger,
    save_file_metadata,
)


def parse_post_file_request(
    checksum: Annotated[str | None, Form()] = None,
) -> UploadFileRequest:
    """Build the typed request schema for `POST /v1/files` form fields."""

    return UploadFileRequest(checksum=checksum)


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

    meta_path = get_meta_path(file_id, cfg)

    # 1. File does not exist -> 404
    if not meta_path.exists():
        logger.warning(
            "file.metadata.not_found",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            FILE_NOT_FOUND,
            details={"file_id": str(file_id)},
        )

    # 2. Try to load + parse metadata
    try:
        raw = meta_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception(
            "file.metadata.read_failed",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INTERNAL_ERROR,
            "Failed to read file metadata.",
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "file.metadata.invalid_json",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Invalid file metadata (corrupted JSON).",
            details={"file_id": str(file_id)},
        ) from exc

    try:
        metadata = FileMetadata.model_validate(payload)
    except Exception as exc:
        logger.warning(
            "file.metadata.invalid_schema",
            extra={"file_id": str(file_id)},
        )
        raise SegError(
            INVALID_REQUEST,
            "Invalid file metadata schema.",
            details={"file_id": str(file_id)},
        ) from exc

    # 3. Success
    logger.info(
        "file.metadata.retrieved",
        extra={"file_id": str(file_id)},
    )

    return metadata


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
        # NOTE: UploadFile stream is consumed during read; cannot be reused.
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
