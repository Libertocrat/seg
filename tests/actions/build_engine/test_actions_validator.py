"""Unit tests for the SEG DSL semantic validator.

These tests freeze validator-layer invariants:
- semantic validation is strict, deterministic, and fail-fast
- module-level and action-level rules are enforced with clear errors
- loader-owned structural parsing is out of scope
"""

from __future__ import annotations

import pytest

from seg.actions.build_engine.validator import validate_modules
from seg.actions.exceptions import ActionSpecsParseError
from seg.actions.schemas import ArgCmd, BinaryCmd, FlagCmd

# ============================================================================
# validate_modules: happy path
# ============================================================================


def test_validate_modules_accepts_valid_module(make_valid_module):
    """
    GIVEN a semantically valid DSL module
    WHEN validate_modules is called
    THEN validation succeeds without raising an exception
    """
    module = make_valid_module()

    validate_modules([module])


# ============================================================================
# module-level validation
# ============================================================================


@pytest.mark.parametrize(
    "version",
    [0, 2, 999],
    ids=["zero", "future", "invalid_large"],
)
def test_validate_modules_rejects_unsupported_version(
    make_module_payload,
    make_module_spec,
    version: int,
):
    """
    GIVEN a module with an unsupported DSL version
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(version=version))

    with pytest.raises(ActionSpecsParseError, match="unsupported DSL version"):
        validate_modules([module])


def test_validate_modules_rejects_empty_binaries(make_module_payload, make_module_spec):
    """
    GIVEN a module with no declared binaries
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(binaries=[]))

    with pytest.raises(ActionSpecsParseError, match="must declare at least one binary"):
        validate_modules([module])


def test_validate_modules_rejects_duplicate_binary_names(
    make_module_payload,
    make_module_spec,
):
    """
    GIVEN a module that declares the same binary twice
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(binaries=["echo", "echo"]))

    with pytest.raises(ActionSpecsParseError, match="duplicate binary 'echo'"):
        validate_modules([module])


def test_validate_modules_rejects_duplicate_module_names(make_valid_module):
    """
    GIVEN two modules with the same module name
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    first = make_valid_module()
    second = make_valid_module()

    with pytest.raises(ActionSpecsParseError, match="duplicate module name"):
        validate_modules([first, second])


def test_validate_modules_rejects_module_without_actions(
    make_module_payload,
    make_module_spec,
):
    """
    GIVEN a module with an empty action mapping
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(actions={}))

    with pytest.raises(ActionSpecsParseError, match="must define at least one action"):
        validate_modules([module])


@pytest.mark.parametrize(
    "name",
    ["", "Invalid", "123abc", "bad-name", "_hidden", "bad name"],
    ids=[
        "empty",
        "uppercase",
        "starts_with_digit",
        "hyphen",
        "leading_underscore",
        "space",
    ],
)
def test_validate_modules_rejects_invalid_module_names(
    make_module_payload,
    make_module_spec,
    name: str,
):
    """
    GIVEN a module whose name violates the DSL naming regex
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(module_name=name))

    with pytest.raises(ActionSpecsParseError, match="invalid module name"):
        validate_modules([module])


@pytest.mark.parametrize(
    "binary_name",
    ["", "Invalid", "123abc", "bad-name", "_hidden", "bad name"],
    ids=[
        "empty",
        "uppercase",
        "starts_with_digit",
        "hyphen",
        "leading_underscore",
        "space",
    ],
)
def test_validate_modules_rejects_invalid_binary_names(
    make_module_payload,
    make_module_spec,
    binary_name: str,
):
    """
    GIVEN a module whose binary name violates the DSL naming regex
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(make_module_payload(binaries=[binary_name]))

    with pytest.raises(ActionSpecsParseError, match="invalid binary name"):
        validate_modules([module])


@pytest.mark.parametrize(
    "tags,error_message",
    [("   ", "tags must be a non-empty CSV string"), ("alpha,,beta", "empty CSV")],
    ids=["blank_tags", "empty_csv_entry"],
)
def test_validate_modules_rejects_invalid_tags(
    make_module_payload,
    make_module_spec,
    tags: str,
    error_message: str,
):
    """
    GIVEN a module with invalid tags metadata
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    payload = make_module_payload()
    payload["tags"] = tags
    module = make_module_spec(payload)

    with pytest.raises(ActionSpecsParseError, match=error_message):
        validate_modules([module])


# ============================================================================
# action-level validation
# ============================================================================


@pytest.mark.parametrize(
    "name",
    ["", "Invalid", "123abc", "bad-name", "_hidden", "bad name"],
    ids=[
        "empty",
        "uppercase",
        "starts_with_digit",
        "hyphen",
        "leading_underscore",
        "space",
    ],
)
def test_validate_modules_rejects_invalid_action_names(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    name: str,
):
    """
    GIVEN an action whose name violates the DSL naming regex
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_module_spec(
        make_module_payload(actions={name: make_action_payload()})
    )

    with pytest.raises(ActionSpecsParseError, match="invalid action name"):
        validate_modules([module])


def test_validate_modules_rejects_empty_command(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an action with an empty command list
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(command=[])
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match="command must not be empty"):
        validate_modules([module])


@pytest.mark.parametrize(
    ("command", "error_message"),
    [
        ([{"arg": "x"}], "exactly one binary token"),
        ([{"binary": "echo"}, {"binary": "cat"}], "exactly one binary token"),
        (["test", {"binary": "echo"}], "binary must be first command element"),
    ],
    ids=["missing_binary", "multiple_binary", "binary_not_first"],
)
def test_validate_modules_rejects_invalid_binary_rules(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    command,
    error_message: str,
):
    """
    GIVEN an action whose command violates binary token rules
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(command=command)
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match=error_message):
        validate_modules([module])


def test_validate_modules_rejects_binary_not_declared_in_module(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an action that references a binary not declared by the module
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(command=[{"binary": "cat"}])
    module = make_module_spec(
        make_module_payload(binaries=["echo", "printf"], actions={"ping": action})
    )

    with pytest.raises(
        ActionSpecsParseError,
        match="is not declared in module binaries",
    ):
        validate_modules([module])


# ============================================================================
# command elements
# ============================================================================


def test_validate_modules_rejects_unsupported_command_element_type(make_valid_module):
    """
    GIVEN a command containing an unsupported element type
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_valid_module()
    module.actions["ping"].command = [BinaryCmd(binary="echo"), 123]

    with pytest.raises(ActionSpecsParseError, match="unsupported element type"):
        validate_modules([module])


@pytest.mark.parametrize(
    ("literal", "error_message"),
    [
        ("", "must not be empty"),
        ("   ", "must not be whitespace-only"),
        ("\x00", "must not contain NULL bytes"),
        ("bad\u0007token", "must not contain control characters"),
    ],
    ids=["empty_literal", "whitespace_only", "null_byte", "control_char"],
)
def test_validate_modules_rejects_invalid_command_literals(
    make_valid_module,
    literal: str,
    error_message: str,
):
    """
    GIVEN a command containing an invalid literal token
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_valid_module()
    module.actions["ping"].command = [BinaryCmd(binary="echo"), literal]

    with pytest.raises(ActionSpecsParseError, match=error_message):
        validate_modules([module])


# ============================================================================
# references
# ============================================================================


def test_validate_modules_rejects_undefined_arg_reference(make_valid_module):
    """
    GIVEN a command that references an undefined argument
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_valid_module()
    module.actions["ping"].command = [BinaryCmd(binary="echo"), ArgCmd(arg="value")]

    with pytest.raises(
        ActionSpecsParseError,
        match="arg 'value' referenced in command but not defined",
    ):
        validate_modules([module])


def test_validate_modules_rejects_undefined_flag_reference(make_valid_module):
    """
    GIVEN a command that references an undefined flag
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    module = make_valid_module()
    module.actions["ping"].command = [BinaryCmd(binary="echo"), FlagCmd(flag="verbose")]

    with pytest.raises(
        ActionSpecsParseError,
        match="flag 'verbose' referenced in command but not defined",
    ):
        validate_modules([module])


# ============================================================================
# unused definitions
# ============================================================================


def test_validate_modules_rejects_unused_arg(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an action that declares an argument but never uses it in command
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "value": {
                "type": "string",
                "required": True,
                "description": "input value",
            }
        },
        command=[{"binary": "echo"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="arg 'value' is defined but not used",
    ):
        validate_modules([module])


def test_validate_modules_rejects_unused_flag(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an action that declares a flag but never uses it in command
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        flags={
            "verbose": {
                "value": "-v",
                "default": False,
                "description": "verbose flag",
            }
        },
        command=[{"binary": "echo"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="flag 'verbose' is defined but not used",
    ):
        validate_modules([module])


# ============================================================================
# naming rules
# ============================================================================


@pytest.mark.parametrize(
    "arg_name",
    ["", "Invalid", "123abc", "bad-name", "_hidden", "bad name"],
    ids=[
        "empty",
        "uppercase",
        "starts_with_digit",
        "hyphen",
        "leading_underscore",
        "space",
    ],
)
def test_validate_modules_rejects_invalid_arg_names(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    arg_name: str,
):
    """
    GIVEN an action whose argument name violates the DSL naming regex
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            arg_name: {
                "type": "string",
                "required": True,
                "description": "input value",
            }
        },
        command=[{"binary": "echo"}, {"arg": arg_name}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match="invalid arg name"):
        validate_modules([module])


@pytest.mark.parametrize(
    "flag_name",
    ["", "Invalid", "123abc", "bad-name", "_hidden", "bad name"],
    ids=[
        "empty",
        "uppercase",
        "starts_with_digit",
        "hyphen",
        "leading_underscore",
        "space",
    ],
)
def test_validate_modules_rejects_invalid_flag_names(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    flag_name: str,
):
    """
    GIVEN an action whose flag name violates the DSL naming regex
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        flags={
            flag_name: {
                "value": "-v",
                "default": False,
                "description": "verbose flag",
            }
        },
        command=[{"binary": "echo"}, {"flag": flag_name}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match="invalid flag name"):
        validate_modules([module])


def test_validate_modules_rejects_arg_flag_name_collisions(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an action that reuses the same name for an arg and a flag
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "dup": {
                "type": "string",
                "required": True,
                "description": "duplicate arg",
            }
        },
        flags={
            "dup": {
                "value": "-d",
                "default": False,
                "description": "duplicate flag",
            }
        },
        command=[{"binary": "echo"}, {"arg": "dup"}, {"flag": "dup"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="name collision between arg and flag 'dup'",
    ):
        validate_modules([module])


# ============================================================================
# argument validation
# ============================================================================


def test_validate_modules_rejects_required_arg_with_default(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN a required arg that also defines a default
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "count": {
                "type": "int",
                "required": True,
                "default": 1,
                "description": "count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="cannot be required and define a default",
    ):
        validate_modules([module])


def test_validate_modules_rejects_optional_arg_without_default(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an optional arg that omits its default
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "count": {
                "type": "int",
                "required": False,
                "description": "count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="must define a default when not required",
    ):
        validate_modules([module])


@pytest.mark.parametrize(
    ("arg_type", "default"),
    [("string", 123), ("bool", "true"), ("float", "3.14")],
    ids=["string_from_int", "bool_from_string", "float_from_string"],
)
def test_validate_modules_rejects_incompatible_default_types(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    arg_type: str,
    default,
):
    """
    GIVEN an arg whose default is incompatible with the declared DSL type
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "value": {
                "type": arg_type,
                "required": False,
                "default": default,
                "description": "value",
            }
        },
        command=[{"binary": "echo"}, {"arg": "value"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="default for arg 'value' is incompatible",
    ):
        validate_modules([module])


def test_validate_modules_rejects_non_integer_float_default_for_int(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN an int arg with a non-integer float default
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "count": {
                "type": "int",
                "required": False,
                "default": 1.5,
                "description": "count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="default for arg 'count' is incompatible",
    ):
        validate_modules([module])


# ============================================================================
# file_id validation
# ============================================================================


def test_validate_modules_rejects_invalid_file_id_default(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN a file_id arg with an invalid UUID4 default
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "file": {
                "type": "file_id",
                "required": False,
                "default": "not-a-uuid4",
                "description": "file id",
            }
        },
        command=[{"binary": "echo"}, {"arg": "file"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="default for arg 'file' is incompatible",
    ):
        validate_modules([module])


# ============================================================================
# constraints
# ============================================================================


def test_validate_modules_rejects_min_max_on_non_numeric_types(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN a non-numeric arg that defines min/max constraints
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "value": {
                "type": "string",
                "required": False,
                "default": "abc",
                "min": 1,
                "description": "value",
            }
        },
        command=[{"binary": "echo"}, {"arg": "value"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="defines min/max but type 'string' is not numeric",
    ):
        validate_modules([module])


def test_validate_modules_rejects_max_size_on_non_file_id(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN a non-file_id arg that defines max_size
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "count": {
                "type": "int",
                "required": False,
                "default": 1,
                "max_size": 10,
                "description": "count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(
        ActionSpecsParseError,
        match="defines max_size but type 'int' is not file_id",
    ):
        validate_modules([module])


def test_validate_modules_rejects_min_greater_than_max(
    make_module_payload,
    make_action_payload,
    make_module_spec,
):
    """
    GIVEN a numeric arg whose min is greater than max
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "count": {
                "type": "int",
                "required": False,
                "default": 5,
                "min": 10,
                "max": 1,
                "description": "count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match="has min greater than max"):
        validate_modules([module])


@pytest.mark.parametrize(
    ("constraints", "error_message"),
    [
        ({"min": 1.5}, "min must be an integer value"),
        ({"max": 2.5}, "max must be an integer value"),
    ],
    ids=["float_min_for_int", "float_max_for_int"],
)
def test_validate_modules_rejects_non_integer_min_max_for_int(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    constraints,
    error_message: str,
):
    """
    GIVEN an int arg with non-integer numeric bounds
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    arg_payload = {
        "type": "int",
        "required": False,
        "default": 5,
        "description": "count",
    }
    arg_payload.update(constraints)

    action = make_action_payload(
        args={"count": arg_payload},
        command=[{"binary": "echo"}, {"arg": "count"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match=error_message):
        validate_modules([module])


@pytest.mark.parametrize(
    "max_size",
    [0, -1],
    ids=["zero", "negative"],
)
def test_validate_modules_rejects_non_positive_max_size(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    max_size: int,
):
    """
    GIVEN a file_id arg with a non-positive max_size
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        args={
            "file": {
                "type": "file_id",
                "required": True,
                "max_size": max_size,
                "description": "file id",
            }
        },
        command=[{"binary": "echo"}, {"arg": "file"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match="max_size must be greater than 0"):
        validate_modules([module])


# ============================================================================
# flags
# ============================================================================


@pytest.mark.parametrize(
    ("flag_value", "error_message"),
    [
        ("", "must not be empty"),
        ("   ", "must not be whitespace-only"),
        ("\x00", "must not contain NULL bytes"),
        ("bad\u0007flag", "must not contain control characters"),
    ],
    ids=["empty", "whitespace_only", "null_byte", "control_char"],
)
def test_validate_modules_rejects_invalid_flag_values(
    make_module_payload,
    make_action_payload,
    make_module_spec,
    flag_value: str,
    error_message: str,
):
    """
    GIVEN a flag whose literal value is invalid
    WHEN validate_modules is called
    THEN ActionSpecsParseError is raised
    """
    action = make_action_payload(
        flags={
            "verbose": {
                "value": flag_value,
                "default": False,
                "description": "verbose flag",
            }
        },
        command=[{"binary": "echo"}, {"flag": "verbose"}],
    )
    module = make_module_spec(make_module_payload(actions={"ping": action}))

    with pytest.raises(ActionSpecsParseError, match=error_message):
        validate_modules([module])
