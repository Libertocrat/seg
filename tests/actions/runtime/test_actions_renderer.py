"""Unit tests for SEG runtime renderer.

These tests validate deterministic argv generation and strict runtime argument
constraints for the SEG DSL action renderer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from pydantic import BaseModel

from seg.actions.exceptions import ActionInvalidArgError, ActionRuntimeRenderError
from seg.actions.models.core import (
    ActionSpec,
    ArgDef,
    CommandElement,
    FlagDef,
    ParamType,
)
from seg.actions.models.security import BinaryPolicy
from seg.actions.runtime.renderer import render_command
from seg.core.schemas.files import FileMetadata


def _make_metadata(file_id, *, size_bytes: int = 10) -> FileMetadata:
    """Build a valid file metadata object for renderer tests.

    Args:
            file_id: File UUID associated with metadata.
            size_bytes: Reported file size in bytes.

    Returns:
            Validated `FileMetadata` instance.
    """

    now = datetime.now(tz=UTC)
    return FileMetadata(
        id=file_id,
        original_filename="input.txt",
        stored_filename=f"file_{file_id}.bin",
        mime_type="text/plain",
        extension=".txt",
        size_bytes=size_bytes,
        sha256="a" * 64,
        created_at=now,
        updated_at=now,
        status="ready",
    )


def _make_spec(
    *,
    arg_defs: dict[str, ArgDef] | None = None,
    flag_defs: dict[str, FlagDef] | None = None,
    defaults: dict[str, object] | None = None,
    command_template: tuple[CommandElement, ...] | None = None,
) -> ActionSpec:
    """Build a minimal valid `ActionSpec` with optional overrides.

    Args:
            arg_defs: Optional runtime argument definitions.
            flag_defs: Optional runtime flag definitions.
            defaults: Optional default params mapping.
            command_template: Optional command token sequence.

    Returns:
            Minimal valid `ActionSpec` ready for renderer tests.
    """

    template = (
        (cast(CommandElement, {"kind": "binary", "value": "echo"}),)
        if command_template is None
        else command_template
    )

    return ActionSpec(
        name="test.echo",
        module="test",
        action="echo",
        version=1,
        params_model=BaseModel,
        binary="echo",
        command_template=template,
        execution_policy=BinaryPolicy(allowed=("echo",), blocked=()),
        arg_defs={} if arg_defs is None else arg_defs,
        flag_defs={} if flag_defs is None else flag_defs,
        defaults={} if defaults is None else defaults,
        authors=None,
        tags=(),
        summary=None,
        description=None,
        deprecated=False,
        params_example=None,
    )


# ============================================================================
# MERGE / DEFAULTS
# ============================================================================


def test_render_command__uses_defaults_when_params_missing():
    """
    GIVEN an action with default argument value
    WHEN render_command is called with empty params
    THEN argv includes the default value
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=False, description="name")
        },
        defaults={"name": "fallback"},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "name"},
        ),
    )

    assert render_command(spec, {}) == ["echo", "fallback"]


def test_render_command__params_override_defaults():
    """
    GIVEN an action with default argument value
    WHEN render_command is called with explicit param
    THEN argv uses param value over default
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=False, description="name")
        },
        defaults={"name": "fallback"},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "name"},
        ),
    )

    assert render_command(spec, {"name": "override"}) == ["echo", "override"]


# ============================================================================
# NONE VALIDATION
# ============================================================================


def test_render_command__rejects_none_values():
    """
    GIVEN a resolved parameter with None value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=False, description="name")
        },
        defaults={"name": None},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "name"},
        ),
    )

    with pytest.raises(ActionInvalidArgError, match="cannot be None"):
        render_command(spec, {})


def test_render_command__rejects_none_in_params():
    """
    GIVEN a parameter explicitly set to None
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=True, description="name")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="cannot be None"):
        render_command(spec, {"name": None})


# ============================================================================
# STRING VALIDATION
# ============================================================================


def test_render_command__rejects_non_string_value():
    """
    GIVEN a string argument receiving a non-string value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="must be a string"):
        render_command(spec, {"value": 123})


def test_render_command__rejects_empty_string():
    """
    GIVEN a string argument with empty string
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="cannot be empty"):
        render_command(spec, {"value": ""})


def test_render_command__rejects_whitespace_string():
    """
    GIVEN a string argument with whitespace-only value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="cannot be empty"):
        render_command(spec, {"value": "   \t"})


@pytest.mark.parametrize(
    "value",
    ["--help", "-v"],
    ids=["double_dash", "single_dash"],
)
def test_render_command__rejects_flag_like_string(value: str):
    """
    GIVEN a string argument with flag-like value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="cannot start with '-'"):
        render_command(spec, {"value": value})


def test_render_command__rejects_flag_like_with_leading_spaces():
    """
    GIVEN a string argument with leading-space flag-like value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="cannot start with '-'"):
        render_command(spec, {"value": "   --danger"})


def test_render_command__accepts_valid_string():
    """
    GIVEN a valid non-empty non-flag string value
    WHEN render_command is called
    THEN argv is rendered successfully
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(type=ParamType.STRING, required=True, description="value")
        },
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "value"},
        ),
    )

    assert render_command(spec, {"value": "hello-world"}) == ["echo", "hello-world"]


# ============================================================================
# NUMERIC VALIDATION
# ============================================================================


def test_render_command__rejects_non_numeric_value():
    """
    GIVEN a numeric argument receiving a non-numeric value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "count": ArgDef(type=ParamType.INT, required=True, description="count")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="must be numeric"):
        render_command(spec, {"count": "abc"})


def test_render_command__enforces_numeric_min():
    """
    GIVEN a numeric argument with minimum constraint
    WHEN value is below minimum
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "count": ArgDef(
                type=ParamType.INT,
                required=True,
                min=5,
                description="count",
            )
        }
    )

    with pytest.raises(
        ActionInvalidArgError,
        match="must be greater than or equal",
    ):
        render_command(spec, {"count": 4})


def test_render_command__enforces_numeric_max():
    """
    GIVEN a numeric argument with maximum constraint
    WHEN value is above maximum
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "count": ArgDef(
                type=ParamType.FLOAT,
                required=True,
                max=2.5,
                description="count",
            )
        }
    )

    with pytest.raises(ActionInvalidArgError, match="must be less than or equal"):
        render_command(spec, {"count": 3.0})


def test_render_command__accepts_valid_float_value():
    """
    GIVEN a float argument within allowed range
    WHEN render_command is called
    THEN argv is rendered successfully
    """

    spec = _make_spec(
        arg_defs={
            "value": ArgDef(
                type=ParamType.FLOAT,
                required=True,
                min=1.0,
                max=5.0,
                description="value",
            )
        },
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "value"},
        ),
    )

    assert render_command(spec, {"value": 3.5}) == ["echo", "3.5"]


# ============================================================================
# FILE_ID RESOLUTION
# ============================================================================


def test_render_command__resolves_file_id_to_blob_path(
    monkeypatch,
    tmp_path: Path,
):
    """
    GIVEN a valid file_id argument
    WHEN metadata and blob are available
    THEN argv uses the resolved blob path
    """

    file_id = uuid4()
    blob_path = tmp_path / f"file_{file_id}.bin"
    blob_path.write_bytes(b"ok")

    monkeypatch.setattr(
        "seg.actions.runtime.renderer.load_file_metadata",
        lambda _: _make_metadata(file_id, size_bytes=2),
    )
    monkeypatch.setattr(
        "seg.actions.runtime.renderer.get_blob_path",
        lambda _: blob_path,
    )

    spec = _make_spec(
        arg_defs={
            "file": ArgDef(type=ParamType.FILE_ID, required=True, description="file")
        },
        command_template=(
            {"kind": "binary", "value": "cat"},
            {"kind": "arg", "name": "file"},
        ),
    )

    assert render_command(spec, {"file": file_id}) == ["cat", str(blob_path)]


def test_render_command__fails_when_file_metadata_is_missing(monkeypatch):
    """
    GIVEN a file_id argument
    WHEN metadata cannot be loaded
    THEN ActionInvalidArgError is raised
    """

    file_id = uuid4()

    monkeypatch.setattr(
        "seg.actions.runtime.renderer.load_file_metadata",
        lambda _: None,
    )
    monkeypatch.setattr(
        "seg.actions.runtime.renderer.get_blob_path",
        lambda _: Path("/unused"),
    )

    spec = _make_spec(
        arg_defs={
            "file": ArgDef(type=ParamType.FILE_ID, required=True, description="file")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="was not found"):
        render_command(spec, {"file": file_id})


def test_render_command__fails_when_blob_path_is_missing(monkeypatch, tmp_path: Path):
    """
    GIVEN a file_id argument with existing metadata
    WHEN blob file is missing on disk
    THEN ActionInvalidArgError is raised
    """

    file_id = uuid4()
    missing_blob_path = tmp_path / "missing.bin"

    monkeypatch.setattr(
        "seg.actions.runtime.renderer.load_file_metadata",
        lambda _: _make_metadata(file_id, size_bytes=10),
    )
    monkeypatch.setattr(
        "seg.actions.runtime.renderer.get_blob_path",
        lambda _: missing_blob_path,
    )

    spec = _make_spec(
        arg_defs={
            "file": ArgDef(type=ParamType.FILE_ID, required=True, description="file")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="blob"):
        render_command(spec, {"file": file_id})


def test_render_command__fails_when_file_size_exceeds_max_size(
    monkeypatch,
    tmp_path: Path,
):
    """
    GIVEN a file_id argument with max_size constraint
    WHEN metadata size exceeds max_size
    THEN ActionInvalidArgError is raised
    """

    file_id = uuid4()
    blob_path = tmp_path / f"file_{file_id}.bin"
    blob_path.write_bytes(b"ok")

    monkeypatch.setattr(
        "seg.actions.runtime.renderer.load_file_metadata",
        lambda _: _make_metadata(file_id, size_bytes=999),
    )
    monkeypatch.setattr(
        "seg.actions.runtime.renderer.get_blob_path",
        lambda _: blob_path,
    )

    spec = _make_spec(
        arg_defs={
            "file": ArgDef(
                type=ParamType.FILE_ID,
                required=True,
                max_size=100,
                description="file",
            )
        },
        command_template=(
            {"kind": "binary", "value": "cat"},
            {"kind": "arg", "name": "file"},
        ),
    )

    with pytest.raises(ActionInvalidArgError, match="file size must be"):
        render_command(spec, {"file": file_id})


def test_render_command__fails_when_file_id_is_invalid_uuid():
    """
    GIVEN a file_id argument with malformed UUID value
    WHEN render_command is called
    THEN ActionInvalidArgError is raised
    """

    spec = _make_spec(
        arg_defs={
            "file": ArgDef(type=ParamType.FILE_ID, required=True, description="file")
        }
    )

    with pytest.raises(ActionInvalidArgError, match="valid file_id"):
        render_command(spec, {"file": "not-a-uuid"})


# ============================================================================
# FLAGS
# ============================================================================


@pytest.mark.parametrize(
    "value",
    [1, "true", object()],
    ids=["int_one", "string_true", "object_instance"],
)
def test_render_command__flag_requires_strict_true(value: object):
    """
    GIVEN a flag parameter with truthy non-True value
    WHEN render_command is called
    THEN flag token is not included
    """

    spec = _make_spec(
        flag_defs={"verbose": FlagDef(value="-v", default=False, description="v")},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "flag", "name": "verbose"},
        ),
    )

    assert render_command(spec, {"verbose": value}) == ["echo"]


def test_render_command__default_false_flag_is_excluded():
    """
    GIVEN a flag with default False
    WHEN params omit the flag
    THEN flag token is excluded from argv
    """

    spec = _make_spec(
        flag_defs={"verbose": FlagDef(value="-v", default=False, description="v")},
        defaults={"verbose": False},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "flag", "name": "verbose"},
        ),
    )

    assert render_command(spec, {}) == ["echo"]


def test_render_command__default_true_flag_is_included():
    """
    GIVEN a flag with default True
    WHEN params omit the flag
    THEN flag token is included in argv
    """

    spec = _make_spec(
        flag_defs={"verbose": FlagDef(value="-v", default=True, description="v")},
        defaults={"verbose": True},
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "flag", "name": "verbose"},
        ),
    )

    assert render_command(spec, {}) == ["echo", "-v"]


# ============================================================================
# COMMAND TEMPLATE
# ============================================================================


def test_render_command__preserves_command_token_order():
    """
    GIVEN mixed binary/const/arg tokens
    WHEN render_command is called
    THEN argv preserves template token order
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=True, description="name")
        },
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "const", "value": "-n"},
            {"kind": "arg", "name": "name"},
            {"kind": "const", "value": "!"},
        ),
    )

    assert render_command(spec, {"name": "seg"}) == ["echo", "-n", "seg", "!"]


def test_render_command__supports_multiple_args_and_flags():
    """
    GIVEN a command template with multiple args and flags
    WHEN render_command is called
    THEN argv includes all resolved values in template order
    """

    spec = _make_spec(
        arg_defs={
            "first": ArgDef(type=ParamType.STRING, required=True, description="first"),
            "second": ArgDef(type=ParamType.INT, required=True, description="second"),
        },
        flag_defs={
            "verbose": FlagDef(value="-v", default=False, description="v"),
            "debug": FlagDef(value="--debug", default=False, description="d"),
        },
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "flag", "name": "verbose"},
            {"kind": "arg", "name": "first"},
            {"kind": "flag", "name": "debug"},
            {"kind": "arg", "name": "second"},
        ),
    )

    assert render_command(
        spec,
        {"first": "abc", "second": 7, "verbose": True, "debug": False},
    ) == ["echo", "-v", "abc", "7"]


# ============================================================================
# EDGE CASES
# ============================================================================


def test_render_command__wraps_unexpected_errors(monkeypatch):
    """
    GIVEN an unexpected internal runtime exception
    WHEN render_command is called
    THEN ActionRuntimeRenderError is raised
    """

    spec = _make_spec(
        arg_defs={
            "name": ArgDef(type=ParamType.STRING, required=True, description="name")
        },
        command_template=(
            {"kind": "binary", "value": "echo"},
            {"kind": "arg", "name": "name"},
        ),
    )

    def _explode(*_args, **_kwargs):
        """Raise a deterministic runtime failure for error-wrapping tests."""
        raise RuntimeError("boom")

    monkeypatch.setattr("seg.actions.runtime.renderer._validate_arg", _explode)

    with pytest.raises(ActionRuntimeRenderError, match="Unexpected failure"):
        render_command(spec, {"name": "safe"})
