# src/seg/actions/dispatcher.py
from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from seg.actions.registry import get_action
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.execute import ExecuteRequest


class SegActionError(Exception):
    """
    Handlers can raise this to force a structured failure without leaking internals.
    Keep it simple: code/message/details.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


async def dispatch_execute(req: ExecuteRequest) -> ResponseEnvelope[Any]:
    logger = logging.getLogger("seg.actions.dispatcher")
    spec = get_action(req.action)
    if spec is None:
        return ResponseEnvelope.failure(
            code="ACTION_NOT_FOUND",
            message="Unsupported action.",
            details={"action": req.action},
        )

    # Validate params with the action-specific Pydantic model
    try:
        params_obj = spec.params_model.model_validate(req.params)
    except ValidationError as exc:
        return ResponseEnvelope.failure(
            code="INVALID_PARAMS",
            message="Invalid params for action.",
            details={"errors": exc.errors()},
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
                return ResponseEnvelope.failure(
                    code="INVALID_RESULT",
                    message="Handler returned invalid result.",
                    details={"errors": exc.errors()},
                )
            return ResponseEnvelope.success_response(validated)

        return ResponseEnvelope.success_response(result)
    except SegActionError as exc:
        return ResponseEnvelope.failure(
            code=exc.code, message=exc.message, details=exc.details
        )
    except TimeoutError:
        return ResponseEnvelope.failure(code="TIMEOUT", message="Operation timed out.")
    except Exception:
        # Log the unexpected exception for operational diagnostics but do not
        # expose internals to the client. The logger will capture stack trace.
        logger.exception("Unhandled exception while executing action %s", req.action)
        return ResponseEnvelope.failure(
            code="INTERNAL_ERROR",
            message="Unhandled error while executing action.",
        )
