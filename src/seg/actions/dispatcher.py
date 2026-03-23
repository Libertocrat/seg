"""Dispatcher for SEG action execution requests."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from seg.actions.registry import get_action
from seg.core.errors import (
    ACTION_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_RESULT,
    TIMEOUT,
    SegError,
)
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.execute import ExecuteRequest


async def dispatch_execute(req: ExecuteRequest) -> tuple[ResponseEnvelope[Any], int]:
    """Validate and execute a requested action.

    Args:
        req: Parsed execution request containing the action name and params.

    Returns:
        A tuple containing the normalized response envelope and HTTP status code.
    """

    logger = logging.getLogger("seg.actions.dispatcher")
    spec = get_action(req.action)
    if spec is None:
        return (
            ResponseEnvelope.failure(
                code=ACTION_NOT_FOUND.code,
                message=ACTION_NOT_FOUND.default_message,
                details={"action": req.action},
            ),
            ACTION_NOT_FOUND.http_status,
        )

    # Validate params with the action-specific Pydantic model
    try:
        params_obj = spec.params_model.model_validate(req.params)
    except ValidationError as exc:
        return (
            ResponseEnvelope.failure(
                code=INVALID_PARAMS.code,
                message=INVALID_PARAMS.default_message,
                details={"errors": exc.errors()},
            ),
            INVALID_PARAMS.http_status,
        )

    # Execute handler + normalize expected errors
    try:
        result = await spec.handler(params_obj)
        # If the action exposes a `result_model`, validate/normalize the
        # handler output against it so the returned `ResponseEnvelope.data`
        # is a clean Pydantic model instance (or a validated plain value).
        result_model = spec.result_model
        if result_model is not None:
            try:
                validated = result_model.model_validate(result)
            except ValidationError as exc:
                return (
                    ResponseEnvelope.failure(
                        code=INVALID_RESULT.code,
                        message=INVALID_RESULT.default_message,
                        details={"errors": exc.errors()},
                    ),
                    INVALID_RESULT.http_status,
                )
            return ResponseEnvelope.success_response(validated), 200

        return ResponseEnvelope.success_response(result), 200
    except SegError as exc:
        return (
            ResponseEnvelope.failure(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            exc.http_status,
        )
    except TimeoutError:
        return (
            ResponseEnvelope.failure(
                code=TIMEOUT.code,
                message=TIMEOUT.default_message,
            ),
            TIMEOUT.http_status,
        )
    except Exception:
        # Log the unexpected exception for operational diagnostics but do not
        # expose internals to the client. The logger will capture stack trace.
        logger.exception("Unhandled exception while executing action %s", req.action)
        return (
            ResponseEnvelope.failure(
                code=INTERNAL_ERROR.code,
                message=INTERNAL_ERROR.default_message,
            ),
            INTERNAL_ERROR.http_status,
        )
