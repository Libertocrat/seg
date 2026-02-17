from __future__ import annotations

from typing import Any

from seg.core.errors import ErrorDef


class SegActionError(Exception):
    def __init__(
        self,
        error: ErrorDef,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.code = error.code
        self.http_status = error.http_status
        self.message = message or error.default_message
        self.details = details or {}
        super().__init__(self.message)
