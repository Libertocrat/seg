from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from seg.core.schemas.envelope import ResponseEnvelope

router = APIRouter(prefix="", tags=["health"])


class HealthResult(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=ResponseEnvelope[HealthResult])
async def health() -> ResponseEnvelope[HealthResult]:
    """Health check endpoint.

    Returns a minimal readiness payload as defined in the SRS.

    Returns:
        A JSONResponse containing the readiness status, e.g. `{"status": "ok"}`.
    """

    return ResponseEnvelope.success_response(HealthResult(status="ok"))
