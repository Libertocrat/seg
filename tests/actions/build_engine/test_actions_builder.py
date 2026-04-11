"""Unit tests for the SEG DSL specs builder.

These tests freeze builder-layer invariants:
- validated `ModuleSpec` input compiles into runtime `ActionSpec`
- runtime contract fields are normalized deterministically
- defensive builder failures are surfaced with `ActionSpecsBuildError`
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from seg.actions.build_engine.builder import build_actions
from seg.actions.exceptions import ActionSpecsBuildError
from seg.actions.models import ActionSpec, ParamType
from seg.core.config import Settings

# ============================================================================
# Fixtures and helpers
# ============================================================================


def _test_settings(
    *,
    blocked_extra: str | None = None,
) -> Settings:
    """Build minimal runtime settings for builder tests.

    Args:
        blocked_extra: Optional CSV blocklist extra entries.

    Returns:
        Validated Settings instance for build_actions.
    """

    return Settings.model_validate(
        {
            "seg_root_dir": "/tmp/seg-test",  # noqa: S108 -- fixed path for testing purposes
            "seg_blocked_binaries_extra": blocked_extra,
        }
    )


# ============================================================================
# build_actions: happy path
# ============================================================================


def test_build_actions_returns_dict(make_valid_module):
    """
    GIVEN a valid module specification
    WHEN build_actions is called
    THEN a dictionary of ActionSpec values is returned
    """
    module = make_valid_module()

    result = build_actions([module], _test_settings())

    assert isinstance(result, dict)
    assert all(isinstance(key, str) for key in result)
    assert all(isinstance(value, ActionSpec) for value in result.values())


# ============================================================================
# namespacing
# ============================================================================


def test_action_names_are_namespaced(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN a module and action
    WHEN build_actions is called
    THEN the resulting key uses `module.action` namespacing
    """
    action = make_action_spec_input()
    module = make_module_spec(
        make_module_payload(module_name="random_gen", actions={"token_hex": action})
    )

    result = build_actions([module], _test_settings())

    assert "random_gen.token_hex" in result


# ============================================================================
# command_template
# ============================================================================


def test_command_template_structure(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action command with binary, arg, and flag tokens
    WHEN build_actions is called
    THEN command_template is a tuple preserving normalized token ordering
    """
    action = make_action_spec_input(
        args={
            "value": {
                "type": "string",
                "required": True,
                "description": "value",
            }
        },
        flags={
            "verbose": {
                "value": "-v",
                "default": False,
                "description": "verbose",
            }
        },
        command=[
            {"binary": "echo"},
            {"flag": "verbose"},
            {"arg": "value"},
        ],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    spec = build_actions([module], _test_settings())["test_module.test_action"]

    assert isinstance(spec.command_template, tuple)
    assert spec.command_template == (
        {"kind": "binary", "value": "echo"},
        {"kind": "flag", "name": "verbose"},
        {"kind": "arg", "name": "value"},
    )


def test_command_template_normalizes_literal_as_const_token(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action command containing a literal element
    WHEN build_actions is called
    THEN the literal is compiled as a `kind='const'` token
    """
    action = make_action_spec_input(command=[{"binary": "echo"}, "-hex"])
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    spec = build_actions([module], _test_settings())["test_module.test_action"]

    assert spec.command_template[1] == {"kind": "const", "value": "-hex"}


# ============================================================================
# binary extraction
# ============================================================================


def test_binary_extracted_from_command(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action command with a binary token
    WHEN build_actions is called
    THEN ActionSpec.binary matches that token value
    """
    action = make_action_spec_input(command=[{"binary": "openssl"}, "rand", "-hex"])
    module = make_module_spec(
        make_module_payload(binaries=["openssl"], actions={"token_hex": action})
    )

    spec = build_actions([module], _test_settings())["test_module.token_hex"]

    assert spec.binary == "openssl"


# ============================================================================
# arg_defs
# ============================================================================


def test_arg_defs_compiled_correctly(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action with argument metadata and constraints
    WHEN build_actions is called
    THEN arg_defs preserve the validated DSL definition
    """
    action = make_action_spec_input(
        args={
            "bytes": {
                "type": "int",
                "required": False,
                "default": 16,
                "min": 1,
                "max": 64,
                "description": "bytes count",
            }
        },
        command=[{"binary": "echo"}, {"arg": "bytes"}],
    )
    module = make_module_spec(make_module_payload(actions={"token_hex": action}))

    spec = build_actions([module], _test_settings())["test_module.token_hex"]
    arg_def = spec.arg_defs["bytes"]

    assert arg_def.type == ParamType.INT
    assert arg_def.required is False
    assert arg_def.default == 16
    assert arg_def.min == 1
    assert arg_def.max == 64


# ============================================================================
# flag_defs
# ============================================================================


def test_flag_defs_compiled_correctly(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action with a flag definition
    WHEN build_actions is called
    THEN flag_defs preserve literal and default values
    """
    action = make_action_spec_input(
        flags={
            "verbose": {
                "value": "-v",
                "default": False,
                "description": "verbose",
            }
        },
        command=[{"binary": "echo"}, {"flag": "verbose"}],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    spec = build_actions([module], _test_settings())["test_module.test_action"]
    flag_def = spec.flag_defs["verbose"]

    assert flag_def.value == "-v"
    assert flag_def.default is False


# ============================================================================
# defaults
# ============================================================================


def test_defaults_include_optional_args_and_flags(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN required and optional args plus flags
    WHEN build_actions is called
    THEN defaults include optional args and all flags, but not required args
    """
    action = make_action_spec_input(
        args={
            "required_arg": {
                "type": "string",
                "required": True,
                "description": "required",
            },
            "optional_arg": {
                "type": "int",
                "required": False,
                "default": 10,
                "description": "optional",
            },
        },
        flags={
            "verbose": {
                "value": "-v",
                "default": True,
                "description": "verbose",
            }
        },
        command=[
            {"binary": "echo"},
            {"arg": "required_arg"},
            {"arg": "optional_arg"},
            {"flag": "verbose"},
        ],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    spec = build_actions([module], _test_settings())["test_module.test_action"]

    assert spec.defaults == {"optional_arg": 10, "verbose": True}


# ============================================================================
# params_model
# ============================================================================


def test_params_model_fields(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN an action with args and flags
    WHEN build_actions is called
    THEN params_model exposes matching field names and annotations
    """
    action = make_action_spec_input(
        args={
            "bytes": {
                "type": "int",
                "required": False,
                "default": 16,
                "description": "bytes",
            },
            "name": {
                "type": "string",
                "required": True,
                "description": "name",
            },
        },
        flags={
            "verbose": {
                "value": "-v",
                "default": False,
                "description": "verbose",
            }
        },
        command=[
            {"binary": "echo"},
            {"arg": "bytes"},
            {"arg": "name"},
            {"flag": "verbose"},
        ],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    model = build_actions([module], _test_settings())[
        "test_module.test_action"
    ].params_model

    assert set(model.model_fields.keys()) == {"bytes", "name", "verbose"}
    assert model.model_fields["bytes"].annotation is int
    assert model.model_fields["name"].annotation is str
    assert model.model_fields["verbose"].annotation is bool


def test_params_model_required_behavior(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN required and optional params in one action
    WHEN validating input through params_model
    THEN missing required params fail and optional params get defaults
    """
    action = make_action_spec_input(
        args={
            "name": {
                "type": "string",
                "required": True,
                "description": "name",
            },
            "count": {
                "type": "int",
                "required": False,
                "default": 2,
                "description": "count",
            },
        },
        flags={
            "verbose": {
                "value": "-v",
                "default": False,
                "description": "verbose",
            }
        },
        command=[
            {"binary": "echo"},
            {"arg": "name"},
            {"arg": "count"},
            {"flag": "verbose"},
        ],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))
    model = build_actions([module], _test_settings())[
        "test_module.test_action"
    ].params_model

    with pytest.raises(ValidationError):
        model.model_validate({})

    validated = model.model_validate({"name": "alice"})
    assert validated.count == 2
    assert validated.verbose is False


def test_file_id_validates_uuid4(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN a file_id parameter
    WHEN validating request params
    THEN invalid UUID values fail and valid UUID4 values pass
    """
    action = make_action_spec_input(
        args={
            "file": {
                "type": "file_id",
                "required": True,
                "description": "file id",
            }
        },
        command=[{"binary": "echo"}, {"arg": "file"}],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))
    model = build_actions([module], _test_settings())[
        "test_module.test_action"
    ].params_model

    with pytest.raises(ValidationError):
        model.model_validate({"file": "not-a-uuid"})

    valid = model.model_validate({"file": str(uuid4())})
    assert valid.file is not None


# ============================================================================
# params_model naming
# ============================================================================


def test_params_model_name_generation(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN a namespaced action identifier with underscore segments
    WHEN build_actions is called
    THEN params_model name follows CamelCase + Params suffix
    """
    action = make_action_spec_input(command=[{"binary": "openssl"}, "rand", "-hex"])
    module = make_module_spec(
        make_module_payload(
            module_name="random_gen",
            binaries=["openssl"],
            actions={"token_hex": action},
        )
    )

    spec = build_actions([module], _test_settings())["random_gen.token_hex"]

    assert spec.params_model.__name__ == "RandomGenTokenHexParams"


# ============================================================================
# tags normalization
# ============================================================================


def test_tags_normalization(
    make_module_payload,
    make_module_spec,
):
    """
    GIVEN a module with mixed-case and duplicate CSV tags
    WHEN build_actions is called
    THEN tags are lowercased, deduplicated, and order-preserving
    """
    payload = make_module_payload()
    payload["tags"] = "A, b, a , C"
    module = make_module_spec(payload)

    spec = build_actions([module], _test_settings())["test_module.ping"]

    assert spec.tags == ("a", "b", "c")


# ============================================================================
# authors normalization
# ============================================================================


def test_authors_normalization(
    make_module_payload,
    make_module_spec,
):
    """
    GIVEN a module with authors metadata
    WHEN build_actions is called
    THEN authors are exposed as a tuple in runtime ActionSpec
    """
    payload = make_module_payload()
    payload["authors"] = ["Alice", "Bob"]
    module = make_module_spec(payload)

    spec = build_actions([module], _test_settings())["test_module.ping"]

    assert spec.authors == ("Alice", "Bob")


# ============================================================================
# duplicate detection
# ============================================================================


def test_duplicate_action_names_raise_error(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN two modules producing the same fully qualified action name
    WHEN build_actions is called
    THEN ActionSpecsBuildError is raised defensively
    """
    action = make_action_spec_input()
    first = make_module_spec(
        make_module_payload(module_name="dup", actions={"ping": action})
    )
    second = make_module_spec(
        make_module_payload(module_name="dup", actions={"ping": action})
    )

    with pytest.raises(ActionSpecsBuildError, match="duplicate fully qualified"):
        build_actions([first, second], _test_settings())


# ============================================================================
# defensive errors
# ============================================================================


def test_missing_binary_raises_error(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN a command template without a binary token
    WHEN build_actions is called
    THEN ActionSpecsBuildError is raised during binary extraction
    """
    action = make_action_spec_input(
        args={
            "value": {
                "type": "string",
                "required": True,
                "description": "value",
            }
        },
        command=[{"arg": "value"}],
    )
    module = make_module_spec(make_module_payload(actions={"test_action": action}))

    with pytest.raises(ActionSpecsBuildError, match="no binary token found"):
        build_actions([module], _test_settings())


def test_invalid_command_element_raises_error(make_valid_module):
    """
    GIVEN a validated module mutated with an unsupported command element
    WHEN build_actions is called
    THEN ActionSpecsBuildError is raised
    """
    module = make_valid_module()
    module.actions["ping"].command = [123]

    with pytest.raises(ActionSpecsBuildError, match="unsupported type"):
        build_actions([module], _test_settings())


# ============================================================================
# immutability
# ============================================================================


def test_input_not_mutated(
    make_module_payload,
    make_module_spec,
    make_action_spec_input,
):
    """
    GIVEN a validated ModuleSpec used as builder input
    WHEN build_actions is called
    THEN the original input module remains unchanged
    """
    action = make_action_spec_input(command=[{"binary": "echo"}, "-n"])
    module = make_module_spec(make_module_payload(actions={"test_action": action}))
    before = module.model_dump(mode="python")

    _ = build_actions([module], _test_settings())

    after = module.model_dump(mode="python")
    assert after == before


def test_build_actions_attaches_execution_policy(make_valid_module):
    """
    GIVEN a valid module and default runtime settings
    WHEN build_actions is called
    THEN each ActionSpec includes an execution_policy
    """
    module = make_valid_module()

    spec = build_actions([module], _test_settings())["test_module.ping"]

    assert spec.execution_policy.allowed == ("echo",)
    assert "bash" in spec.execution_policy.blocked


def test_build_actions_merges_blocked_extra(make_valid_module):
    """
    GIVEN a valid module and blocked extra values
    WHEN build_actions is called
    THEN extra binaries are merged into the effective blocklist
    """
    module = make_valid_module()

    spec = build_actions(
        [module],
        _test_settings(blocked_extra="openssl"),
    )["test_module.ping"]

    assert "openssl" in spec.execution_policy.blocked


def test_build_actions_fails_when_primary_binary_is_blocked_extra(
    make_valid_module,
):
    """
    GIVEN a valid module and blocked extra matching action binary
    WHEN build_actions is called
    THEN ActionSpecsBuildError is raised fail-closed
    """
    module = make_valid_module()

    with pytest.raises(ActionSpecsBuildError, match="is not allowed by effective"):
        build_actions([module], _test_settings(blocked_extra="echo"))


def test_build_actions_blocklist_wins_module_allowlist(make_valid_module):
    """
    GIVEN a module-allowed binary also present in blocked extra entries
    WHEN build_actions is called
    THEN the binary is excluded from effective allowlist
    """
    module = make_valid_module()

    with pytest.raises(ActionSpecsBuildError, match="is not allowed by effective"):
        build_actions(
            [module],
            _test_settings(blocked_extra="echo"),
        )
