"""HTTP routes for SEG-managed file resources.

This module exposes the first RESTful file endpoint for ingesting uploads and
returning typed SEG response envelopes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import VerifyChecksumParams
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.files import UploadFileData, UploadFileRequest
from seg.routes.handlers.files import ingest_uploaded_file, parse_post_file_request

router = APIRouter(prefix="/v1", tags=["Files"])

description = (
    "Upload and securely persist a file using SEG-managed storage.\n\n"
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


@router.post(
    "/files",
    status_code=201,
    summary="Upload and persist a file",
    description=description,
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
        metadata = await ingest_uploaded_file(file, verify_checksum=verify_checksum)
        return ResponseEnvelope.success_response(UploadFileData(file=metadata))
    except SegActionError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())
