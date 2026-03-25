"""Pydantic schemas for SEG file upload responses and persisted metadata.

This module defines strongly validated contracts used by file ingestion and
the `POST /v1/files` response payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FileMetadata(BaseModel):
    """Typed metadata persisted for each stored file.

    Attributes:
        id: Stable UUID assigned by SEG for the uploaded file.
        original_filename: Client-supplied filename after basename normalization.
        stored_filename: Internal blob filename persisted by SEG.
        mime_type: Server-detected MIME type in `type/subtype` form.
        extension: Normalized lowercase extension including leading dot.
        size_bytes: Persisted file size in bytes.
        sha256: Lowercase SHA-256 digest as 64 hex characters.
        created_at: UTC timestamp when the record was created.
        updated_at: UTC timestamp when the record was last updated.
        status: Lifecycle state of the file metadata.
    """

    id: UUID
    original_filename: str = Field(..., min_length=1)
    stored_filename: str = Field(..., min_length=1)
    mime_type: str = Field(..., pattern=r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
    extension: str = Field(..., pattern=r"^\.[a-z0-9]+$")
    size_bytes: int = Field(..., ge=0)
    sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    updated_at: datetime
    status: Literal["ready"] = "ready"


class UploadFileData(BaseModel):
    """Success payload for `POST /v1/files`.

    Attributes:
        file: Persisted metadata for the uploaded file.
    """

    file: FileMetadata


class UploadFileRequest(BaseModel):
    """Input schema for `POST /v1/files` multipart form fields.

    Attributes:
        checksum: Optional SHA-256 checksum provided by the client.
    """

    checksum: str | None = Field(
        default=None,
        description="Optional SHA-256 checksum provided by the client.",
    )


class DeleteFileResult(BaseModel):
    """Delete result payload for a previously stored file.

    Attributes:
        id: UUID of the deleted file.
        deleted: Deletion success flag.
    """

    id: UUID
    deleted: bool


class DeleteFileData(BaseModel):
    """Success payload for `DELETE /v1/files/{id}`.

    Attributes:
        file: Structured delete outcome.
    """

    file: DeleteFileResult
