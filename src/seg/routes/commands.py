# src/seg/routes/commands.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..actions.file_hash import FileNotFoundErrorSafe, FileTooLargeError, sha256_file
from ..core.config import settings
from ..core.schemas.envelope import ResponseEnvelope
from ..core.schemas.execute import ExecuteRequest, Sha256FileResult
from ..core.security.paths import PathSecurityError, resolve_under_root

router = APIRouter(prefix="/v1", tags=["commands"])


@router.post("/execute", response_model=ResponseEnvelope[Sha256FileResult])
async def execute(req: ExecuteRequest) -> ResponseEnvelope[Sha256FileResult]:
    # Minimal allowlist: only one action in v1 commit
    if req.action != "sha256_file":
        return ResponseEnvelope.failure(
            code="ACTION_NOT_FOUND",
            message="Unsupported action for this minimal version.",
            details={"action": req.action},
        )

    # Extract param
    path_raw = req.params.get("path")
    if not isinstance(path_raw, str):
        return ResponseEnvelope.failure(
            code="INVALID_PARAMS",
            message="Expected params.path as string.",
        )

    # Resolve within root
    root = Path(settings.seg_fs_root)
    try:
        path = resolve_under_root(root=root, user_path=path_raw)
    except PathSecurityError as exc:
        return ResponseEnvelope.failure(
            code="PATH_NOT_ALLOWED",
            message=str(exc),
        )

    # Execute
    try:
        digest, size_bytes = await sha256_file(path)
    except FileNotFoundErrorSafe:
        return ResponseEnvelope.failure(
            code="FILE_NOT_FOUND",
            message="File not found.",
        )
    except FileTooLargeError:
        return ResponseEnvelope.failure(
            code="FILE_TOO_LARGE",
            message="File exceeds maximum allowed size.",
            details={"max_bytes": settings.seg_max_bytes},
        )
    except TimeoutError:
        return ResponseEnvelope.failure(
            code="TIMEOUT",
            message="Operation timed out.",
            details={"timeout_ms": settings.seg_timeout_ms},
        )

    return ResponseEnvelope.success_response(
        Sha256FileResult(sha256=digest, size_bytes=size_bytes)
    )
