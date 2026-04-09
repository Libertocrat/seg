"""HTTP routes for SEG-managed file resources.

This module exposes the first RESTful file endpoint for ingesting uploads and
returning typed SEG response envelopes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from seg.core.errors import SegError
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.utils.file_storage import iter_file_chunks
from seg.routes.files.handlers.delete_file import delete_file_handler
from seg.routes.files.handlers.get_file_content import get_file_content_handler
from seg.routes.files.handlers.get_file_metadata import get_file_metadata_handler
from seg.routes.files.handlers.list_files import list_files_handler
from seg.routes.files.handlers.upload_file import (
    parse_post_file_request,
    upload_file_handler,
)
from seg.routes.files.schemas import (
    DeleteFileData,
    FileListData,
    UploadFileData,
    UploadFileRequest,
    VerifyChecksumParams,
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


list_files_description = (
    "**List SEG-managed files with cursor pagination and deterministic ordering.**\n\n"
    "Supports filtering by `status`, `mime_type`, and `extension`, with "
    "sorting by `created_at` and stable tiebreaking by file id."
)


@router.get(
    "/files",
    summary="List stored files",
    description=list_files_description,
    response_model=ResponseEnvelope[FileListData],
)
async def list_files(
    limit: int = 20,
    cursor: str | None = None,
    sort: str = "created_at",
    order: str = "asc",
    status: str | None = None,
    mime_type: str | None = None,
    extension: str | None = None,
) -> JSONResponse | ResponseEnvelope[FileListData]:
    """List persisted files using cursor pagination."""

    try:
        result = await list_files_handler(
            limit=limit,
            cursor=cursor,
            sort=sort,
            order=order,
            status=status,
            mime_type=mime_type,
            extension=extension,
        )
        return ResponseEnvelope.success_response(result)
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())


get_content_description = (
    "**Stream the binary contents of a previously uploaded file managed by SEG.**\n\n"
    "This endpoint resolves the file through SEG metadata, validates that the "
    "file is in ready state, and returns the blob as a streamed download "
    "response.\n\n"
    "Behavior:\n"
    "- Validates the provided file identifier (UUID)\n"
    "- Loads metadata from SEG-managed storage\n"
    "- Verifies that the file is available for download\n"
    "- Streams the file content without loading the entire blob into memory\n\n"
    "Security considerations:\n"
    "- No direct filesystem paths are exposed\n"
    "- Only SEG-managed file identifiers are accepted\n"
    "- Access is controlled via SEG authentication middleware\n"
)


@router.get(
    "/files/{id}/content",
    summary="Download file content",
    description=get_content_description,
    response_model=None,  # Response is a streamed binary, not JSON
    responses={
        200: {
            "description": "Streamed file content.",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
            "headers": {
                "Content-Disposition": {
                    "description": "Download filename",
                    "schema": {"type": "string"},
                },
                "Content-Length": {
                    "description": "Size of the file in bytes",
                    "schema": {"type": "integer"},
                },
            },
        }
    },
)
async def get_file_content(id: UUID):
    """Stream file content by UUID."""

    try:
        descriptor = await get_file_content_handler(file_id=id)

        headers = {
            "Content-Disposition": f'attachment; filename="{descriptor.filename}"',
        }

        if descriptor.size_bytes is not None:
            headers["Content-Length"] = str(descriptor.size_bytes)

        return StreamingResponse(
            iter_file_chunks(descriptor.blob_path),
            media_type=descriptor.mime_type,
            headers=headers,
        )
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())


delete_description = (
    "**Hard-delete a previously uploaded file managed by SEG.**\n\n"
    "This endpoint resolves the file through SEG metadata and removes both "
    "storage artifacts in strict order:\n"
    "- blob (`files/blobs/file_<uuid>.bin`)\n"
    "- metadata (`files/meta/file_<uuid>.json`)\n\n"
    "Deletion is only allowed when file metadata is in `ready` state."
)


@router.delete(
    "/files/{id}",
    summary="Delete a stored file",
    description=delete_description,
    response_model=ResponseEnvelope[DeleteFileData],
)
async def delete_file(id: UUID) -> JSONResponse | ResponseEnvelope[DeleteFileData]:
    """Delete file blob + metadata by UUID."""

    try:
        result = await delete_file_handler(file_id=id)
        return ResponseEnvelope.success_response(DeleteFileData(file=result))
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())
