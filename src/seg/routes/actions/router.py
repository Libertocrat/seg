"""HTTP route that exposes SEG's action execution endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from seg.core.errors import SegError
from seg.core.schemas.envelope import ResponseEnvelope
from seg.routes.actions.handlers.execute_action import execute_action_handler
from seg.routes.actions.schemas import ExecuteActionData, ExecuteRequest

router = APIRouter(prefix="/v1", tags=["execute"])


@router.post("/execute", response_model=ResponseEnvelope[ExecuteActionData])
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
