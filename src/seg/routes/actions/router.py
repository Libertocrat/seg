"""HTTP route that exposes SEG's action execution endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from seg.core.errors import SegError
from seg.core.schemas.envelope import ResponseEnvelope
from seg.routes.actions.handlers.execute_action import execute_action_handler
from seg.routes.actions.handlers.list_actions import list_actions_handler
from seg.routes.actions.schemas import (
    ExecuteActionData,
    ExecuteRequest,
    ListActionsData,
)

router = APIRouter(prefix="/v1", tags=["Actions"])


@router.get(
    "/actions",
    response_model=ResponseEnvelope[ListActionsData],
    summary="List available actions grouped by module with optional filtering.",
)
async def list_actions(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
) -> JSONResponse | ResponseEnvelope[ListActionsData]:
    """List DSL-defined actions grouped by module with optional filtering."""

    try:
        result = await list_actions_handler(request, q=q, tag=tag)
        return ResponseEnvelope.success_response(result)
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())


@router.post(
    "/execute",
    response_model=ResponseEnvelope[ExecuteActionData],
    summary="Execute a registered action with given parameters.",
)
async def execute(
    request: Request,
    req: ExecuteRequest,
) -> JSONResponse | ResponseEnvelope[ExecuteActionData]:
    """Execute an allow-listed DSL action via the runtime handler."""

    try:
        data = await execute_action_handler(request, req)
        return ResponseEnvelope.success_response(data)
    except SegError as exc:
        payload = ResponseEnvelope.failure(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.http_status, content=payload.model_dump())
