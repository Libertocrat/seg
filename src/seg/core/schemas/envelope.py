# src/seg/core/schemas/envelope.py
from __future__ import annotations

from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

T = TypeVar("T")


class ErrorInfo(BaseModel):
    code: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")
    details: Optional[dict[str, Any]] = Field(
        default=None, description="Optional details."
    )


class ResponseEnvelope(GenericModel, Generic[T]):
    """Standard HTTP response envelope used across services.

    Fields follow the README contract: `success`, `data`, and `error`.
    Request correlation is performed via the `X-Request-Id` header injected
    by middleware; the JSON body deliberately omits `request_id`.
    """

    success: bool = Field(..., description="Success flag.")
    data: Optional[T] = Field(default=None, description="Result payload on success.")
    error: Optional[ErrorInfo] = Field(
        default=None, description="Error payload on failure."
    )

    @classmethod
    def success_response(cls, data: T) -> "ResponseEnvelope[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ResponseEnvelope[Any]":
        return cls(
            success=False,
            data=None,
            error=ErrorInfo(code=code, message=message, details=details),
        )
