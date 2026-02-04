from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.schemas.envelope import ResponseEnvelope

router = APIRouter(prefix="", tags=["health"])


@router.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    """Health check endpoint.

    Returns a minimal readiness payload as defined in the SRS.

    Returns:
        A JSONResponse containing the readiness status, e.g. `{"status": "ok"}`.
    """

    payload = ResponseEnvelope.success_response({"status": "ok"}).model_dump()
    return JSONResponse(payload)
