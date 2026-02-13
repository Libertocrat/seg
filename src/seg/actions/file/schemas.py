"""Schemas for file-related actions.

This module centralizes Pydantic models used by file action handlers.

Design notes and conventions:
- Models live next to their handlers and represent the stable contract
    between the dispatcher and action implementations.
- Naming: use `<ActionName>Params` for input models and
    `<ActionName>Result` for output models (for example, `ChecksumParams`).
- Params models should be strict and explicit. Result models represent
    the handler output and must not include HTTP concepts (status codes).
- Keep models free of business logic; they are intended only for
    validation and documentation.

This module will host many action schemas over time; keep models small
and well-documented to support automatic schema discovery and docs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Lightweight enum for algorithms supported in v1. Expand as needed.
Algorithm = Literal["sha256", "md5", "sha1"]


class ChecksumParams(BaseModel):
    """Parameters for the `file_checksum` action.

    Attributes:
        path (str): Path string provided by the client. Interpreted as a path
            relative to the configured SEG sandbox directory and must be resolved
            via the centralized security helpers before use.
        algorithm (str): Digest algorithm to use. Defaults to "sha256".
    """

    path: str = Field(..., description="Path relative to SEG sandbox directory.")
    algorithm: Algorithm = Field(
        "sha256",
        description="Hash algorithm to use (allowed: sha256, md5, sha1).",
    )


class ChecksumResult(BaseModel):
    """Result returned by the `file_checksum` action.

    Attributes:
        algorithm (str): Algorithm actually used (lowercased string).
        checksum (str): Hexadecimal digest string.
        size_bytes (int): Size of the file in bytes that was processed.
    """

    algorithm: str = Field(..., description="Algorithm used for the checksum.")
    checksum: str = Field(..., description="Hexadecimal digest string.")
    size_bytes: int = Field(..., description="Size of the file in bytes.")


class DeleteParams(BaseModel):
    """Parameters for the `file_delete` action.

    Attributes:
        path (str): Relative path under SEG_SANDBOX_DIR to delete.
        require_exists (bool): If True, a missing target results in FILE_NOT_FOUND;
            if False, the operation is idempotent and returns deleted=False.
    """

    path: str = Field(..., description="Relative path under SEG_SANDBOX_DIR to delete")
    require_exists: bool = Field(
        False, description="If true, missing target results in FILE_NOT_FOUND"
    )


class DeleteResult(BaseModel):
    """Result returned by the `file_delete` action.

    Attributes:
        deleted (bool): True if a file was deleted, False if it did not exist.
    """

    deleted: bool = Field(
        ..., description="True if a file was deleted, false if it did not exist"
    )


class MimeDetectParams(BaseModel):
    """Parameters for the `file_mime_detect` action."""

    path: str = Field(
        ...,
        description="Path relative to SEG sandbox directory.",
    )


class MimeDetectResult(BaseModel):
    """Result returned by the `file_mime_detect` action."""

    mime: str = Field(
        ...,
        description="Detected MIME type using content-based analysis.",
    )


# Public exports for clarity and documentation tooling.
__all__ = [
    "Algorithm",
    "ChecksumParams",
    "ChecksumResult",
    "DeleteParams",
    "DeleteResult",
    "MimeDetectParams",
    "MimeDetectResult",
]
