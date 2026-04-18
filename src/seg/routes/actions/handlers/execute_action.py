"""Route handler for SEG `/v1/execute` runtime orchestration."""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import Request
from pydantic import ValidationError

from seg.actions.dispatcher import dispatch_action
from seg.actions.exceptions import (
    ActionBinaryBlockedError,
    ActionBinaryNotAllowedError,
    ActionBinaryPathForbiddenError,
    ActionExecutionTimeoutError,
    ActionInvalidArgError,
    ActionNotFoundError,
    ActionRuntimeExecError,
    ActionRuntimeRenderError,
)
from seg.actions.registry import ActionRegistry
from seg.actions.runtime.sanitizer import (
    DEFAULT_MAX_STDERR_BYTES,
    DEFAULT_MAX_STDOUT_BYTES,
    transform_output,
)
from seg.core.config import Settings, get_settings
from seg.core.errors import (
    ACTION_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    PERMISSION_DENIED,
    TIMEOUT,
    SegError,
)
from seg.routes.actions.schemas import ExecuteActionData, ExecuteRequest


def _encode_output(data: bytes) -> tuple[str, Literal["utf-8", "base64"]]:
    """Encode process output bytes for JSON transport."""

    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return base64.b64encode(data).decode("ascii"), "base64"


def _get_action_registry(request: Request) -> ActionRegistry:
    """Resolve and validate the action registry from application state.

    Args:
            request: FastAPI request instance.

    Returns:
            Runtime ActionRegistry instance.

    Raises:
            SegError: If registry is missing or invalid in app state.
    """
    registry = getattr(request.app.state, "action_registry", None)
    if not isinstance(registry, ActionRegistry):
        raise SegError(
            INTERNAL_ERROR,
            message="Action registry is not available.",
        )
    return registry


async def execute_action_handler(
    request: Request,
    payload: ExecuteRequest,
) -> ExecuteActionData:
    """Execute one DSL action and map runtime exceptions to `SegError`."""

    registry = _get_action_registry(request)

    try:
        result = await dispatch_action(registry, payload.action, payload.params)
    except ActionNotFoundError as exc:
        raise SegError(
            ACTION_NOT_FOUND,
            message=f"Action '{payload.action}' is not supported.",
            details={"action": payload.action},
        ) from exc
    except ValidationError as exc:
        raise SegError(
            INVALID_PARAMS,
            details={"errors": exc.errors()},
        ) from exc
    except ActionInvalidArgError as exc:
        raise SegError(
            INVALID_PARAMS,
            details={"reason": str(exc)},
        ) from exc
    except ActionRuntimeRenderError as exc:
        raise SegError(
            INVALID_REQUEST,
            details={"reason": str(exc)},
        ) from exc
    except ActionBinaryBlockedError as exc:
        raise SegError(
            PERMISSION_DENIED,
            details={"reason": str(exc)},
        ) from exc
    except ActionBinaryNotAllowedError as exc:
        raise SegError(
            PERMISSION_DENIED,
            details={"reason": str(exc)},
        ) from exc
    except ActionBinaryPathForbiddenError as exc:
        raise SegError(
            PERMISSION_DENIED,
            details={"reason": str(exc)},
        ) from exc
    except ActionExecutionTimeoutError as exc:
        raise SegError(TIMEOUT) from exc
    except ActionRuntimeExecError as exc:
        raise SegError(INTERNAL_ERROR, details={"reason": str(exc)}) from exc
    except Exception as exc:
        raise SegError(
            INTERNAL_ERROR,
            details={"reason": "unexpected error"},
        ) from exc

    settings = getattr(request.app.state, "settings", None)
    cfg = settings if isinstance(settings, Settings) else get_settings()

    max_stdout = getattr(cfg, "seg_max_stdout_bytes", None) or DEFAULT_MAX_STDOUT_BYTES
    max_stderr = getattr(cfg, "seg_max_stderr_bytes", None) or DEFAULT_MAX_STDERR_BYTES

    safe = transform_output(
        result,
        max_stdout=max_stdout,
        max_stderr=max_stderr,
    )

    stdout, stdout_encoding = _encode_output(safe.stdout)
    stderr, stderr_encoding = _encode_output(safe.stderr)

    return ExecuteActionData(
        exit_code=safe.returncode,
        stdout=stdout,
        stdout_encoding=stdout_encoding,
        stderr=stderr,
        stderr_encoding=stderr_encoding,
        exec_time=safe.exec_time,
        pid=safe.pid,
        truncated=safe.truncated,
        redacted=safe.redacted,
    )
