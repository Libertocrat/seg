from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="", tags=["health"])


@router.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    """Health check endpoint.

    Returns a minimal readiness payload as defined in the SRS.
    """
    return JSONResponse({"status": "ok"})
