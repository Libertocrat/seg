"""Schemas for action execution and discovery endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from seg.routes.files.schemas import FileMetadata


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
    outputs: dict[str, FileMetadata | None] | None = None


class ActionSummarySchema(BaseModel):
    """Public summary payload for one registered action."""

    action: str
    action_id: str
    summary: str | None
    description: str | None


class ModuleSummarySchema(BaseModel):
    """Public summary payload for one DSL module."""

    module: str
    module_id: str
    namespace: str
    namespace_path: list[str]
    description: str | None
    tags: list[str]
    authors: list[str]
    actions: list[ActionSummarySchema]


class ListActionsData(BaseModel):
    """Success payload for `GET /v1/actions`."""

    modules: list[ModuleSummarySchema]


class GetActionData(BaseModel):
    """Success payload for `GET /v1/actions/{action_id}`."""

    action: str
    action_id: str
    summary: str | None
    description: str | None
    args: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    params_schema: dict[str, Any]
    response_schema: dict[str, Any]
