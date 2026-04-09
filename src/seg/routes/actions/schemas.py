"""Request schema for the `/v1/execute` endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Client request body for executing a registered SEG action."""

    action: str = Field(..., description="Action name, e.g. file_checksum.")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters."
    )


class ExecuteActionData(BaseModel):
    """Typed success payload for the `/v1/execute` endpoint."""

    exit_code: int
    stdout: str
    stdout_encoding: Literal["utf-8", "base64"]
    stderr: str
    stderr_encoding: Literal["utf-8", "base64"]
    exec_time: float
    pid: int | None = None
    truncated: bool
    redacted: bool
