from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDef:
    code: str
    http_status: int
    default_message: str


ACTION_NOT_FOUND = ErrorDef(
    code="ACTION_NOT_FOUND",
    http_status=404,
    default_message="Unsupported action.",
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

INVALID_RESULT = ErrorDef(
    code="INVALID_RESULT",
    http_status=500,
    default_message="Handler returned invalid result.",
)

PATH_NOT_ALLOWED = ErrorDef(
    code="PATH_NOT_ALLOWED",
    http_status=403,
    default_message="Path not allowed.",
)

FILE_NOT_FOUND = ErrorDef(
    code="FILE_NOT_FOUND",
    http_status=404,
    default_message="File not found.",
)

FILE_TOO_LARGE = ErrorDef(
    code="FILE_TOO_LARGE",
    http_status=413,
    default_message="File exceeds maximum allowed size.",
)

PERMISSION_DENIED = ErrorDef(
    code="PERMISSION_DENIED",
    http_status=403,
    default_message="Permission denied.",
)

TIMEOUT = ErrorDef(
    code="TIMEOUT",
    http_status=504,
    default_message="Operation timed out.",
)

INTERNAL_ERROR = ErrorDef(
    code="INTERNAL_ERROR",
    http_status=500,
    default_message="Unhandled error while executing action.",
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

CONFLICT = ErrorDef(
    code="CONFLICT",
    http_status=409,
    default_message="Resource conflict.",
)

RATE_LIMITED = ErrorDef(
    code="RATE_LIMITED",
    http_status=429,
    default_message="Rate limit exceeded.",
)


__all__ = [
    "ErrorDef",
    "ACTION_NOT_FOUND",
    "INVALID_PARAMS",
    "INVALID_RESULT",
    "PATH_NOT_ALLOWED",
    "FILE_NOT_FOUND",
    "FILE_TOO_LARGE",
    "PERMISSION_DENIED",
    "TIMEOUT",
    "INTERNAL_ERROR",
    "INVALID_ALGORITHM",
    "FILE_EXTENSION_MISSING",
    "MIME_MAPPING_NOT_DEFINED",
    "INVALID_REQUEST",
    "UNAUTHORIZED",
    "CONFLICT",
    "RATE_LIMITED",
]
