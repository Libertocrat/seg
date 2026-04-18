"""Output sanitization and truncation layer for SEG runtime execution."""

from __future__ import annotations

import re

from seg.actions.models import ActionExecutionOutput, ActionExecutionResult

DEFAULT_MAX_STDOUT_BYTES = 64 * 1024
DEFAULT_MAX_STDERR_BYTES = 64 * 1024

TRUNCATION_MARKER = b"\n[SEG OUTPUT TRUNCATED]\n"
PATH_REDACTION = "[REDACTED_PATH]"

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<!:)(?<![A-Za-z0-9._-])/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+"
)


def sanitize_output(data: bytes) -> bytes:
    """Sanitize subprocess output.

    Steps:
        - Decode using UTF-8 with replacement
        - Remove ANSI escape sequences
        - Strip unsafe control characters
        - Normalize line endings
        - Redact absolute paths
        - Re-encode to UTF-8

    Args:
        data: Raw output bytes.

    Returns:
        Sanitized bytes.
    """

    if not data:
        return b""

    text = data.decode("utf-8", errors="replace")
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _UNSAFE_CONTROL_RE.sub("", text)
    text = _ABSOLUTE_PATH_RE.sub(PATH_REDACTION, text)
    return text.encode("utf-8", errors="replace")


def truncate_output(data: bytes, limit: int) -> tuple[bytes, bool]:
    """Truncate output safely with marker.

    Args:
        data: Input bytes.
        limit: Maximum allowed size.

    Returns:
        Tuple of (truncated_data, was_truncated).
    """

    if len(data) <= limit:
        return data, False

    marker_len = len(TRUNCATION_MARKER)
    if limit <= marker_len:
        return TRUNCATION_MARKER[:limit], True

    keep = limit - marker_len
    return data[:keep] + TRUNCATION_MARKER, True


def transform_output(
    result: ActionExecutionResult,
    *,
    max_stdout: int,
    max_stderr: int,
) -> ActionExecutionOutput:
    """Transform raw execution output into a sanitized and bounded result.

    Args:
        result: Raw execution result from executor.
        max_stdout: Maximum allowed stdout size in bytes.
        max_stderr: Maximum allowed stderr size in bytes.

    Returns:
        Sanitized and truncated execution output.

    Raises:
        ValueError: If limits are invalid.
    """

    if max_stdout <= 0:
        raise ValueError("max_stdout must be greater than 0")
    if max_stderr <= 0:
        raise ValueError("max_stderr must be greater than 0")

    stdout_sanitized = sanitize_output(result.stdout)
    stderr_sanitized = sanitize_output(result.stderr)

    stdout_safe, stdout_truncated = truncate_output(stdout_sanitized, max_stdout)
    stderr_safe, stderr_truncated = truncate_output(stderr_sanitized, max_stderr)

    marker_bytes = PATH_REDACTION.encode()
    stdout_redacted = marker_bytes in stdout_sanitized
    stderr_redacted = marker_bytes in stderr_sanitized

    return ActionExecutionOutput(
        returncode=result.returncode,
        stdout=stdout_safe,
        stderr=stderr_safe,
        exec_time=result.exec_time,
        pid=result.pid,
        truncated=stdout_truncated or stderr_truncated,
        redacted=stdout_redacted or stderr_redacted,
    )
