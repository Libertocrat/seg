"""Request schema for the `/v1/execute` endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Client request body for executing a registered SEG action."""

    action: str = Field(..., description="Action name, e.g. file_checksum.")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters."
    )
