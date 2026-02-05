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
    """Input parameters for the `checksum_file` action.

    Fields
    - path: A path string provided by the client. It is interpreted as a
        path relative to the configured SEG root and must be resolved via
        the centralized security helpers before use.
    - algorithm: The digest algorithm to use. Defaults to ``"sha256"``.
    """

    path: str = Field(..., description="Path relative to SEG root.")
    algorithm: Algorithm = Field(
        "sha256",
        description="Hash algorithm to use (allowed: sha256, md5, sha1).",
    )


class ChecksumResult(BaseModel):
    """Normalized result for the `checksum_file` action.

    Fields
    - algorithm: The algorithm actually used (lowercased string).
    - checksum: Hexadecimal digest string.
    - size_bytes: Size of the file in bytes that was processed.
    """

    algorithm: str = Field(..., description="Algorithm used for the checksum.")
    checksum: str = Field(..., description="Hexadecimal digest string.")
    size_bytes: int = Field(..., description="Size of the file in bytes.")


# Public exports for clarity and documentation tooling.
__all__ = ["Algorithm", "ChecksumParams", "ChecksumResult"]
