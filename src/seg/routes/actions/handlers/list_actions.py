"""Route handler for SEG `GET /v1/actions` discovery endpoint."""

from __future__ import annotations

from fastapi import Request

from seg.actions.presentation.catalog import filter_modules
from seg.actions.presentation.serializers import modules_to_response
from seg.core.errors import INTERNAL_ERROR, INVALID_PARAMS, SegError
from seg.routes.actions.schemas import ListActionsData


def _validate_query_param(value: str | None, name: str) -> str | None:
    """Normalize and validate an optional query parameter value.

    Args:
        value: Raw query parameter value.
        name: Query parameter name for error context.

    Returns:
        Normalized query value or None when unset.

    Raises:
        SegError: If the parameter contains disallowed characters.
    """

    if value is None:
        return None

    value = value.strip()

    # Basic hardening: reject NUL bytes in query values.
    if "\x00" in value:
        raise SegError(
            INVALID_PARAMS,
            f"Invalid {name} parameter.",
            details={"param": name},
        )

    return value


async def list_actions_handler(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
) -> ListActionsData:
    """List available SEG actions grouped by module with optional filters.

    Args:
        request: Incoming FastAPI request.
        q: Optional free-text filter for action fields.
        tag: Optional module tag filter.

    Returns:
        Typed discovery payload for module summaries.

    Raises:
        SegError: If registry access, validation, or filtering fails.
    """

    try:
        registry = getattr(request.app.state, "action_registry", None)
        if registry is None:
            raise SegError(INTERNAL_ERROR, "Action registry not available.")

        q = _validate_query_param(q, "q")
        tag = _validate_query_param(tag, "tag")

        modules = registry.module_summaries
        filtered = filter_modules(modules, q=q, tag=tag)
        response_dict = modules_to_response(filtered)

        return ListActionsData(**response_dict)
    except SegError:
        raise
    except Exception as exc:
        raise SegError(INTERNAL_ERROR, "Failed to list actions.") from exc
