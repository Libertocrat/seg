"""Pydantic DSL schemas for arguments, flags, and command tokens."""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict

from seg.actions.models import ParamType


class ArgSpec(BaseModel):
    """Definition of an argument in the SEG DSL."""

    model_config = ConfigDict(extra="forbid")

    type: ParamType
    required: Optional[bool] = False
    default: Optional[Any] = None
    constraints: Optional[dict[str, Any]] = None

    description: str


class FlagSpec(BaseModel):
    """Definition of a flag in the SEG DSL."""

    value: str
    default: bool
    description: str


class BinaryCmd(BaseModel):
    """DSL token representing the selected binary."""

    binary: str


class ArgCmd(BaseModel):
    """DSL token referencing a defined argument."""

    arg: str


class FlagCmd(BaseModel):
    """DSL token referencing a defined flag."""

    flag: str


CommandElement = Union[str, BinaryCmd, ArgCmd, FlagCmd]
