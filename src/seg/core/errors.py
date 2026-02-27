"""Centralized HTTP error definitions shared across SEG."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDef:
    code: str
    http_status: int
    default_message: str


BAD_REQUEST = ErrorDef(
    code="BAD_REQUEST",
    http_status=400,
    default_message="Bad request.",
)

INVALID_PARAMS = ErrorDef(
    code="INVALID_PARAMS",
    http_status=400,
    default_message="Invalid params for action.",
)

INVALID_REQUEST = ErrorDef(
    code="INVALID_REQUEST",
    http_status=400,
    default_message="Invalid request.",
)

INVALID_ALGORITHM = ErrorDef(
    code="INVALID_ALGORITHM",
    http_status=400,
    default_message="Unsupported checksum algorithm.",
)

FILE_EXTENSION_MISSING = ErrorDef(
    code="FILE_EXTENSION_MISSING",
    http_status=400,
    default_message="Cannot infer MIME type because file has no extension.",
)

MIME_MAPPING_NOT_DEFINED = ErrorDef(
    code="MIME_MAPPING_NOT_DEFINED",
    http_status=400,
    default_message="No MIME mapping defined for file extension.",
)

UNAUTHORIZED = ErrorDef(
    code="UNAUTHORIZED",
    http_status=401,
    default_message="Authentication required or invalid token.",
)

PATH_NOT_ALLOWED = ErrorDef(
    code="PATH_NOT_ALLOWED",
    http_status=403,
    default_message="Path not allowed.",
)

PERMISSION_DENIED = ErrorDef(
    code="PERMISSION_DENIED",
    http_status=403,
    default_message="Permission denied.",
)

RESOURCE_NOT_FOUND = ErrorDef(
    code="RESOURCE_NOT_FOUND",
    http_status=404,
    default_message="Resource not found.",
)

ACTION_NOT_FOUND = ErrorDef(
    code="ACTION_NOT_FOUND",
    http_status=404,
    default_message="Unsupported action.",
)

FILE_NOT_FOUND = ErrorDef(
    code="FILE_NOT_FOUND",
    http_status=404,
    default_message="File not found.",
)

METHOD_NOT_ALLOWED = ErrorDef(
    code="METHOD_NOT_ALLOWED",
    http_status=405,
    default_message="HTTP method not allowed for this path.",
)

CONFLICT = ErrorDef(
    code="CONFLICT",
    http_status=409,
    default_message="Resource conflict.",
)

FILE_TOO_LARGE = ErrorDef(
    code="FILE_TOO_LARGE",
    http_status=413,
    default_message="File exceeds maximum allowed size.",
)

UNSUPPORTED_MEDIA_TYPE = ErrorDef(
    code="UNSUPPORTED_MEDIA_TYPE",
    http_status=415,
    default_message="Unsupported media type.",
)

UNPROCESSABLE_ENTITY = ErrorDef(
    code="UNPROCESSABLE_ENTITY",
    http_status=422,
    default_message="Unprocessable entity.",
)

RATE_LIMITED = ErrorDef(
    code="RATE_LIMITED",
    http_status=429,
    default_message="Rate limit exceeded.",
)

INVALID_RESULT = ErrorDef(
    code="INVALID_RESULT",
    http_status=500,
    default_message="Handler returned invalid result.",
)

INTERNAL_ERROR = ErrorDef(
    code="INTERNAL_ERROR",
    http_status=500,
    default_message="Unhandled error while executing action.",
)

TIMEOUT = ErrorDef(
    code="TIMEOUT",
    http_status=504,
    default_message="Operation timed out.",
)

PUBLIC_HTTP_ERRORS = [
    BAD_REQUEST,
    INVALID_PARAMS,
    INVALID_REQUEST,
    INVALID_ALGORITHM,
    FILE_EXTENSION_MISSING,
    MIME_MAPPING_NOT_DEFINED,
    UNAUTHORIZED,
    PATH_NOT_ALLOWED,
    PERMISSION_DENIED,
    RESOURCE_NOT_FOUND,
    ACTION_NOT_FOUND,
    FILE_NOT_FOUND,
    METHOD_NOT_ALLOWED,
    CONFLICT,
    FILE_TOO_LARGE,
    UNSUPPORTED_MEDIA_TYPE,
    UNPROCESSABLE_ENTITY,
    RATE_LIMITED,
    INVALID_RESULT,
    INTERNAL_ERROR,
    TIMEOUT,
]

# Errors flagged as public are included in the OpenAPI schema and used by
# FastAPI/Starlette handlers when mapping raw HTTP codes to SEG’s stable
# machine-readable responses.

__all__ = [
    "ErrorDef",
    "PUBLIC_HTTP_ERRORS",
    "BAD_REQUEST",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "INVALID_ALGORITHM",
    "FILE_EXTENSION_MISSING",
    "MIME_MAPPING_NOT_DEFINED",
    "UNAUTHORIZED",
    "PATH_NOT_ALLOWED",
    "PERMISSION_DENIED",
    "RESOURCE_NOT_FOUND",
    "ACTION_NOT_FOUND",
    "FILE_NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "CONFLICT",
    "FILE_TOO_LARGE",
    "UNSUPPORTED_MEDIA_TYPE",
    "UNPROCESSABLE_ENTITY",
    "RATE_LIMITED",
    "INVALID_RESULT",
    "INTERNAL_ERROR",
    "TIMEOUT",
]
