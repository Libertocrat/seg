"""Domain exceptions raised by SEG action handlers."""

from __future__ import annotations

from typing import Any

from seg.core.errors import ErrorDef


class SegActionError(Exception):
    """Structured exception used to return stable action error responses."""

    def __init__(
        self,
        error: ErrorDef,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize a structured action exception.

        Args:
            error: Canonical error definition that provides code and status.
            message: Optional override for the default error message.
            details: Optional machine-readable context for the failure.
        """

        self.code = error.code
        self.http_status = error.http_status
        self.message = message or error.default_message
        self.details = details or {}
        super().__init__(self.message)
