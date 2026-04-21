"""Runtime execution models for SEG actions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


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


@dataclass(frozen=True, slots=True)
class RenderedAction:
    """Rendered action state produced before command execution.

    Attributes:
        argv: Final resolved argv passed to executor.
        output_files: Mapping of output name to SEG file id for `file + command`.
    """

    argv: list[str]
    output_files: dict[str, UUID]

    def __iter__(self):
        """Iterate over argv tokens for backward-compatible list semantics."""

        return iter(self.argv)

    def __len__(self) -> int:
        """Return argv token count for backward-compatible list semantics."""

        return len(self.argv)

    def __getitem__(self, index: int) -> str:
        """Return one argv token by index for backward-compatible access."""

        return self.argv[index]

    def __eq__(self, other: object) -> bool:
        """Compare with another RenderedAction or a plain argv-like list."""

        if isinstance(other, RenderedAction):
            return self.argv == other.argv and self.output_files == other.output_files
        if isinstance(other, list):
            return self.argv == other
        return False
