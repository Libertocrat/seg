# src/seg/core/schemas/execute.py
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    action: str = Field(..., description="Action name, e.g. sha256_file.")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters."
    )


class Sha256FileResult(BaseModel):
    sha256: str
    size_bytes: int


class ExecuteResponse(BaseModel):
    # In this minimal version, we return only sha256_file result when ok=True.
    # Later we will generalize this with a dispatcher + per-action schemas.
    result: Optional[Sha256FileResult] = None
