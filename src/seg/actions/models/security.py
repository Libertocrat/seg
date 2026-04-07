"""Security-related runtime models for SEG actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BinaryPolicy:
    """Execution policy for allowed and blocked binaries."""

    allowed: tuple[str, ...]
    blocked: tuple[str, ...]
