"""Pydantic DSL schema for per-action input definitions."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from .dsl import ArgSpec, CommandElement, FlagSpec


class ActionSpecInput(BaseModel):
    """Raw action definition as declared in the DSL."""

    description: str
    summary: Optional[str] = None

    args: Optional[Dict[str, ArgSpec]] = None
    flags: Optional[Dict[str, FlagSpec]] = None

    command: List[CommandElement]
