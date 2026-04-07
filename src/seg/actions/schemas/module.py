"""Pydantic DSL schema for module-level action definitions."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from .action import ActionSpecInput


class ModuleSpec(BaseModel):
    """Root DSL module definition."""

    version: int
    module: str
    description: str

    authors: Optional[List[str]] = None
    tags: Optional[str] = None

    binaries: List[str]

    actions: Dict[str, ActionSpecInput]
