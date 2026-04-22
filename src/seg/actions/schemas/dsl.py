"""Pydantic DSL schemas for arguments, flags, command tokens, and outputs."""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict

from seg.actions.models import ParamType


class ArgSpec(BaseModel):
    """Definition of an argument in the SEG DSL."""

    model_config = ConfigDict(extra="forbid")

    type: ParamType
    items: ParamType | None = None
    required: Optional[bool] = False
    default: Optional[Any] = None
    constraints: Optional[dict[str, Any]] = None

    description: str


class FlagSpec(BaseModel):
    """Definition of a flag in the SEG DSL."""

    model_config = ConfigDict(extra="forbid")

    value: str
    default: bool
    description: str


class BinaryCmd(BaseModel):
    """DSL token representing the selected binary."""

    model_config = ConfigDict(extra="forbid")

    binary: str


class ArgCmd(BaseModel):
    """DSL token referencing a defined argument."""

    model_config = ConfigDict(extra="forbid")

    arg: str


class FlagCmd(BaseModel):
    """DSL token referencing a defined flag."""

    model_config = ConfigDict(extra="forbid")

    flag: str


class OutputCmd(BaseModel):
    """DSL token referencing a defined output."""

    model_config = ConfigDict(extra="forbid")

    output: str


class OutputSpec(BaseModel):
    """Definition of one output in the SEG DSL."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["file", "data"]
    source: Literal["command", "stdout", "stderr"]
    description: str


CommandElement = Union[str, BinaryCmd, ArgCmd, FlagCmd, OutputCmd]
