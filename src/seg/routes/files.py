"""HTTP routes for SEG-managed file resources.

This module exposes the first RESTful file endpoint for ingesting uploads and
returning typed SEG response envelopes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from seg.actions.file.schemas import VerifyChecksumParams
from seg.core.errors import SegError
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.files import UploadFileData, UploadFileRequest
from seg.routes.handlers.files import (
    get_file_metadata_handler,
    parse_post_file_request,
    upload_file_handler,
)

router = APIRouter(prefix="/v1", tags=["Files"])

post_description = (
    "**Upload and securely persist a file using SEG-managed storage.**\n\n"
    "This endpoint accepts multipart/form-data uploads and enforces a strict "
    "validation pipeline before persisting any data.\n\n"
    "Processing steps:\n"
    "- Stream upload to temporary storage\n"
    "- Compute SHA256 checksum\n"
    "- Detect MIME type using server-side inspection\n"
    "- Validate extension ↔ MIME mapping\n"
    "- Reject executable or unsafe file types\n"
    "- Enforce maximum file size limits\n"
    "- Persist blob and metadata atomically\n\n"
    "Checksum verification:\n"
    "- An optional `checksum` field may be provided\n"
    "- The value MUST be the SHA256 hash (hex-encoded) of the file contents\n"
    "- If provided, SEG verifies integrity before accepting the upload\n"
    "- Mismatches result in request rejection\n\n"
    "Storage model:\n"
    "- Files are stored as immutable blobs\n"
    "- Metadata is persisted as a JSON sidecar document\n"
    "- Each file is identified by a UUID\n\n"
    "Security guarantees:\n"
    "- No trust in client-provided MIME types\n"
    "- Strict extension-to-MIME validation\n"
    "- Executable content is rejected by default\n"
    "- Atomic write operations prevent partial persistence\n"
)

get_metadata_description = (
    "**Retrieve metadata for a previously uploaded file managed by SEG.**\n\n"
    "This endpoint provides read-only access to file metadata stored in the SEG "
    "filesystem-backed storage model. It does not return the file contents.\n\n"
    "Behavior:\n"
    "- Validates the provided file identifier (UUID)\n"
    "- Loads metadata from SEG-managed storage\n"
    "- Returns structured metadata in a standard response envelope\n\n"
    "Storage model:\n"
    "- Files are stored as immutable blobs\n"
    "- Metadata is persisted as a JSON sidecar document\n"
    "- Each file is uniquely identified by a UUID\n\n"
    "Security considerations:\n"
    "- No direct filesystem paths are exposed\n"
    "- No file content is returned by this endpoint\n"
    "- Access is controlled via SEG authentication middleware\n\n"
    "Use cases:\n"
    "- Verify upload success\n"
    "- Inspect file properties (size, type, checksum)\n"
    "- Integrate with automation workflows (e.g., n8n)\n"
)


@router.post(
    "/files",
    status_code=201,
    summary="Upload and persist a file",
    description=post_description,
    response_model=ResponseEnvelope[UploadFileData],
)
async def post_file(
    file: Annotated[UploadFile, File(...)],
    request: Annotated[UploadFileRequest, Depends(parse_post_file_request)],
) -> JSONResponse | ResponseEnvelope[UploadFileData]:
    """Upload a file, validate it, and persist blob + metadata.

    Args:
        file: Multipart uploaded file stream.
        request: Typed request schema for form fields.

    Returns:
        A success response envelope with file metadata, or a JSON error response
        mapped from structured SEG action errors.
    """

    verify_checksum: VerifyChecksumParams | None = None
    if request.checksum:
        try:
            verify_checksum = VerifyChecksumParams(
                expected=request.checksum,
                algorithm="sha256",
            )
        except ValidationError as exc:
            payload = ResponseEnvelope.failure(
                code="INVALID_REQUEST",
                message="Invalid checksum parameter.",
                details={"errors": exc.errors()},
            )
            return JSONResponse(status_code=400, content=payload.model_dump())

    try:
        metadata = await upload_file_handler(file, verify_checksum=verify_checksum)
        return ResponseEnvelope.success_response(UploadFileData(file=metadata))
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())


@router.get(
    "/files/{id}",
    summary="Retrieve file metadata",
    description=get_metadata_description,
    response_model=ResponseEnvelope[UploadFileData],
)
async def get_file(id: UUID) -> JSONResponse | ResponseEnvelope[UploadFileData]:
    """Retrieve file metadata by UUID.

    Args:
        id: File UUID.

    Returns:
        Success envelope with typed file metadata or a structured SEG error response.
    """

    try:
        metadata = await get_file_metadata_handler(file_id=id)
        return ResponseEnvelope.success_response(UploadFileData(file=metadata))
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())
