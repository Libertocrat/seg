"""Runtime execution models for SEG actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    """Execution result returned by the SEG runtime executor."""

    returncode: int
    stdout: bytes
    stderr: bytes
    exec_time: float
    pid: int | None = None


@dataclass(frozen=True, slots=True)
class ActionExecutionOutput:
    """Sanitized execution result safe for external exposure."""

    returncode: int
    stdout: bytes
    stderr: bytes
    exec_time: float
    pid: int | None

    truncated: bool
    redacted: bool
