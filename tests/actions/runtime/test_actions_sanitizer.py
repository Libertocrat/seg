"""Tests for SEG output sanitization and truncation layer."""

from __future__ import annotations

import pytest

from seg.actions.models.runtime import ActionExecutionResult
from seg.actions.runtime.sanitizer import (
    PATH_REDACTION,
    TRUNCATION_MARKER,
    sanitize_output,
    transform_output,
    truncate_output,
)


def _make_result(
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> ActionExecutionResult:
    """Build a deterministic ActionExecutionResult for output tests."""

    return ActionExecutionResult(
        returncode=0,
        stdout=stdout,
        stderr=stderr,
        exec_time=0.01,
        pid=123,
    )


@pytest.mark.parametrize(
    "input_bytes,expected",
    [
        (b"\x1b[31mred\x1b[0m", b"red"),
        (b"a\x00b\x1fc\x7f", b"abc"),
        (b"/tmp/seg/out.txt", PATH_REDACTION.encode("utf-8")),
    ],
    ids=["ansi_strip", "control_chars", "path_redaction"],
)
def test_sanitize_output_applies_security_pipeline(input_bytes: bytes, expected: bytes):
    """GIVEN raw subprocess bytes with unsafe content
    WHEN sanitize_output is called
    THEN the returned bytes are sanitized deterministically
    """

    assert sanitize_output(input_bytes) == expected


def test_sanitize_output_normalizes_newlines():
    """GIVEN mixed newline conventions
    WHEN sanitize_output is called
    THEN line endings are normalized to LF
    """

    assert sanitize_output(b"a\r\nb\rc\n") == b"a\nb\nc\n"


def test_truncate_output_below_limit_keeps_data():
    """GIVEN output smaller than limit
    WHEN truncate_output is called
    THEN bytes are returned unchanged and not truncated
    """

    data = b"hello"
    out, truncated = truncate_output(data, 8)

    assert out == data
    assert truncated is False


def test_truncate_output_above_limit_appends_marker():
    """GIVEN output larger than limit
    WHEN truncate_output is called
    THEN output is truncated and includes truncation marker
    """

    data = b"A" * 128
    limit = 32

    out, truncated = truncate_output(data, limit)

    assert truncated is True
    assert len(out) == limit
    assert out.endswith(TRUNCATION_MARKER)


def test_truncate_output_very_small_limit_returns_marker_slice():
    """GIVEN a limit smaller than marker length
    WHEN truncate_output is called on oversized output
    THEN only a marker slice is returned
    """

    limit = 8
    out, truncated = truncate_output(b"0123456789", limit)

    assert truncated is True
    assert out == TRUNCATION_MARKER[:limit]


def test_truncate_limit_equals_marker():
    """GIVEN limit equal to marker length
    WHEN truncated
    THEN output equals marker slice
    """

    limit = len(TRUNCATION_MARKER)
    out, truncated = truncate_output(b"X" * (limit + 10), limit)

    assert truncated is True
    assert out == TRUNCATION_MARKER[:limit]


def test_postprocess_output_sets_truncated_flag_when_any_stream_is_truncated():
    """GIVEN one stream above truncation limit
    WHEN postprocess_output is called
    THEN truncated flag is true in the aggregated output
    """

    result = _make_result(stdout=b"X" * 128, stderr=b"ok")

    safe = transform_output(result, max_stdout=32, max_stderr=32)

    assert safe.truncated is True


def test_redacted_only_when_path_present():
    """GIVEN output without paths but with normalization changes
    WHEN postprocessed
    THEN redacted is False
    """

    result = _make_result(stdout=b"\x1b[31mhello\x1b[0m\r\n", stderr=b"\x00warn")

    safe = transform_output(result, max_stdout=1024, max_stderr=1024)

    assert safe.redacted is False


def test_redacted_when_path_present():
    """GIVEN output with absolute path
    WHEN postprocessed
    THEN redacted is True
    """

    result = _make_result(stdout=b"\x1b[31m/tmp/seg/secret.txt\x1b[0m", stderr=b"")

    safe = transform_output(result, max_stdout=1024, max_stderr=1024)

    assert safe.redacted is True
    assert PATH_REDACTION.encode("utf-8") in safe.stdout


def test_sanitize_handles_invalid_utf8():
    """GIVEN invalid utf-8 bytes
    WHEN sanitized
    THEN no exception is raised
    """

    out = sanitize_output(b"\xff\xfe\xfa")

    assert isinstance(out, bytes)


def test_postprocess_output_processes_stdout_and_stderr_and_aggregates_flags():
    """GIVEN stdout and stderr requiring sanitization and truncation
    WHEN postprocess_output is called
    THEN both streams are transformed and flags are aggregated correctly
    """

    result = _make_result(
        stdout=b"/very/long/path/that/should/be/redacted\n" + (b"A" * 200),
        stderr=b"\x1b[31mERR\x1b[0m\x00",
    )

    safe = transform_output(result, max_stdout=48, max_stderr=16)

    assert safe.truncated is True
    assert safe.redacted is True
    assert PATH_REDACTION.encode("utf-8") in safe.stdout
    assert b"\x1b" not in safe.stderr
    assert b"\x00" not in safe.stderr


@pytest.mark.parametrize(
    "max_stdout,max_stderr,error_field",
    [
        (0, 1, "max_stdout"),
        (1, 0, "max_stderr"),
    ],
    ids=["zero_limit_stdout", "zero_limit_stderr"],
)
def test_postprocess_rejects_zero_limit(
    max_stdout: int,
    max_stderr: int,
    error_field: str,
):
    """GIVEN zero limits
    WHEN postprocess_output is called
    THEN ValueError is raised
    """

    result = _make_result(stdout=b"ok", stderr=b"ok")

    with pytest.raises(ValueError, match=error_field):
        transform_output(result, max_stdout=max_stdout, max_stderr=max_stderr)
