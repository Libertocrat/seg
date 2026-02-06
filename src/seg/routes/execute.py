# src/seg/routes/execute.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from seg.actions.dispatcher import dispatch_execute
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.execute import ExecuteRequest

router = APIRouter(prefix="/v1", tags=["execute"])


@router.post("/execute", response_model=ResponseEnvelope[Any])
async def execute(req: ExecuteRequest) -> ResponseEnvelope[Any]:
    """HTTP endpoint that delegates action execution to the dispatcher.

    The route is intentionally thin: it validates the HTTP boundary via
    `ExecuteRequest` (FastAPI/Pydantic) and forwards the request to the
    action dispatcher which performs action resolution, params validation
    and execution. The dispatcher returns a `ResponseEnvelope` which the
    route returns directly to the client.
    """

    return await dispatch_execute(req)
