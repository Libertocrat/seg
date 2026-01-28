"""Exception handlers and utilities for the SEG application.

This module exposes two handlers used by the FastAPI app:
- `http_exception_handler`: formats Starlette HTTP exceptions as JSON and
    preserves the request id when available.
- `generic_exception_handler`: logs unhandled exceptions and returns a
    generic 500 response while including request id for correlation.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, cast

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

logger = logging.getLogger("seg.exceptions")


async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle Starlette HTTP exceptions and include request id header.

    Args:
        request: The incoming FastAPI request.
        exc: The Starlette HTTPException being handled.

    Returns:
        A JSONResponse with the original status code and a minimal payload
        containing `detail`. If a `request_id` is available on the
        request state it is added to the `X-Request-Id` response header.
    """

    rid = getattr(request.state, "request_id", None)
    headers = {"X-Request-Id": rid} if rid else {}
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


# `add_exception_handler` has a broader expected type (it accepts handlers for
# `Exception`), so expose a typed alias that satisfies that API while keeping
# the runtime handler signature narrow for clarity and static reasoning.
http_exception_handler: Callable[
    [Request, Exception], Response | Awaitable[Response]
] = cast(
    Callable[[Request, Exception], Response | Awaitable[Response]],
    _http_exception_handler,
)


async def generic_exception_handler(request: Request, exc: Exception):
    """Generic exception handler for unhandled exceptions.

    This handler logs the exception (including the `request_id` when
    available) and returns a 500 Internal Server Error response with a
    minimal payload. The handler guarantees that `X-Request-Id` is present
    in the response when a request id was assigned earlier in the request
    lifecycle.

    Args:
        request: The incoming FastAPI request.
        exc: The exception that was raised.

    Returns:
        A JSONResponse with HTTP 500 and a minimal error payload.
    """

    rid = getattr(request.state, "request_id", None)
    headers = {"X-Request-Id": rid} if rid else {}
    logger.exception("Unhandled exception (request_id=%s): %s", rid, exc)
    return JSONResponse(
        status_code=500, content={"detail": "Internal Server Error"}, headers=headers
    )
