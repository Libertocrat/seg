"""Semantic validator for SEG DSL v1 module specifications.

This module validates already parsed `ModuleSpec` objects and enforces the
security-critical semantic rules of the SEG YAML DSL. Validation is strict,
deterministic, fail-fast, and non-mutating.

The validator is intentionally isolated from runtime execution concerns:

- it does not build runtime `ActionSpec` objects
- it does not interact with the action registry
- it does not normalize or coerce command structures beyond the published rules

Its responsibility is to reject semantically invalid DSL modules before they
can reach any later compilation or runtime layers.
"""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from typing import NoReturn
from uuid import UUID

from seg.actions.exceptions import ActionSpecsParseError
from seg.actions.models.core import ParamType
from seg.actions.schemas.action import ActionSpecInput
from seg.actions.schemas.dsl import ArgCmd, ArgSpec, BinaryCmd, FlagCmd, FlagSpec
from seg.actions.schemas.module import ModuleSpec

logger = logging.getLogger("seg.actions.build_engine.validator")

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_modules(modules: list[ModuleSpec]) -> None:
    """Validate parsed SEG DSL modules for semantic correctness.

    Args:
            modules: Parsed and structurally validated module specifications.

    Raises:
            ActionSpecsParseError: If any semantic validation rule is violated.
    """

    _validate_unique_module_names(modules)

    for module in modules:
        _validate_module(module)


def _validate_unique_module_names(modules: list[ModuleSpec]) -> None:
    """Ensure module names are unique across the input collection.

    Args:
            modules: Parsed module specifications.

    Raises:
            ActionSpecsParseError: If the same module name appears more than once.
    """

    seen: set[str] = set()

    for module in modules:
        if module.module in seen:
            _raise_module_error(
                module.module,
                f"duplicate module name '{module.module}'",
            )
        seen.add(module.module)


def _validate_module(module: ModuleSpec) -> None:
    """Validate one SEG DSL module.

    Args:
            module: Parsed module specification.

    Raises:
            ActionSpecsParseError: If any module-level or action-level rule fails.
    """

    _validate_module_version(module)
    _validate_identifier(
        module_name=module.module,
        identifier_kind="module",
        identifier_value=module.module,
    )
    _validate_module_has_actions(module)
    _validate_module_binaries(module)
    _validate_module_tags(module)

    for action_name, action in module.actions.items():
        _validate_action(module, action_name, action)


def _validate_module_has_actions(module: ModuleSpec) -> None:
    """Ensure a module declares at least one action.

    Args:
            module: Module specification to validate.

    Raises:
            ActionSpecsParseError: If the module action mapping is empty.
    """

    if not module.actions:
        _raise_module_error(module.module, "module must define at least one action")


def _validate_module_version(module: ModuleSpec) -> None:
    """Ensure the module uses the supported DSL version.

    Args:
        module: Module specification to validate.

    Raises:
        ActionSpecsParseError: If the module version is unsupported.
    """

    if module.version != 1:
        _raise_module_error(
            module.module,
            f"unsupported DSL version '{module.version}'; only version 1 is supported",
        )


def _validate_module_binaries(module: ModuleSpec) -> None:
    """Ensure module-level binary declarations are unique.

    Args:
            module: Module specification to validate.

    Raises:
            ActionSpecsParseError: If duplicate binaries are declared.
    """

    if not module.binaries:
        _raise_module_error(module.module, "module must declare at least one binary")

    seen: set[str] = set()

    for binary in module.binaries:
        _validate_identifier(
            module_name=module.module,
            identifier_kind="binary",
            identifier_value=binary,
        )
        if binary in seen:
            _raise_module_error(
                module.module,
                f"duplicate binary '{binary}' declared in module binaries",
            )
        seen.add(binary)


def _validate_module_tags(module: ModuleSpec) -> None:
    """Validate optional module tags as a non-empty CSV string.

    Args:
            module: Module specification to validate.

    Raises:
            ActionSpecsParseError: If the tags field is blank or contains empty
                    CSV tokens.
    """

    if module.tags is None:
        return

    if module.tags.strip() == "":
        _raise_module_error(module.module, "tags must be a non-empty CSV string")

    try:
        rows = list(csv.reader([module.tags]))
    except csv.Error as exc:
        _raise_module_error(
            module.module,
            f"tags must be a valid CSV string ({exc})",
        )

    if not rows or not rows[0]:
        _raise_module_error(module.module, "tags must be a non-empty CSV string")

    tokens = [token.strip() for token in rows[0]]
    if any(token == "" for token in tokens):
        _raise_module_error(
            module.module,
            "tags must not contain empty CSV entries",
        )


def _validate_action(
    module: ModuleSpec,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate one action definition inside a module.

    Args:
            module: Parent module specification.
            action_name: Action name as declared in the module mapping.
            action: Parsed action specification.

    Raises:
            ActionSpecsParseError: If the action is semantically invalid.
    """

    _validate_identifier(
        module_name=module.module,
        identifier_kind="action",
        identifier_value=action_name,
    )
    _validate_command_exists(module.module, action_name, action)
    _validate_name_collisions(module.module, action_name, action)
    _validate_argument_names(module.module, action_name, action)
    _validate_flag_names(module.module, action_name, action)
    _validate_binary_rules(module, action_name, action)
    _validate_command_elements(module.module, action_name, action)
    _validate_command_references(module.module, action_name, action)
    _validate_unused_definitions(module.module, action_name, action)
    _validate_args(module.module, action_name, action)
    _validate_flags(module.module, action_name, action)


def _validate_command_exists(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Ensure the action command list is not empty.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If the command list is empty.
    """

    if not action.command:
        _raise_action_error(module_name, action_name, "command must not be empty")


def _validate_name_collisions(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Ensure action arg and flag names do not overlap.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If an arg name collides with a flag name.
    """

    arg_names = set((action.args or {}).keys())
    flag_names = set((action.flags or {}).keys())

    collisions = sorted(arg_names & flag_names)
    if collisions:
        collision = collisions[0]
        _raise_action_error(
            module_name,
            action_name,
            f"name collision between arg and flag '{collision}'",
        )


def _validate_argument_names(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate all argument names for one action.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If an arg name violates identifier rules.
    """

    for arg_name in (action.args or {}).keys():
        _validate_identifier(
            module_name=module_name,
            identifier_kind="arg",
            identifier_value=arg_name,
            action_name=action_name,
        )


def _validate_flag_names(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate all flag names for one action.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If a flag name violates identifier rules.
    """

    for flag_name in (action.flags or {}).keys():
        _validate_identifier(
            module_name=module_name,
            identifier_kind="flag",
            identifier_value=flag_name,
            action_name=action_name,
        )


def _validate_binary_rules(
    module: ModuleSpec,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate binary token presence, position, and module allowlist.

    Args:
            module: Parent module specification.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If the command violates binary token rules.
    """

    binary_positions = [
        index
        for index, element in enumerate(action.command)
        if isinstance(element, BinaryCmd)
    ]

    if not binary_positions:
        _raise_action_error(
            module.module,
            action_name,
            "command must contain exactly one binary token",
        )

    if len(binary_positions) > 1:
        _raise_action_error(
            module.module,
            action_name,
            "command must contain exactly one binary token",
        )

    if binary_positions[0] != 0:
        _raise_action_error(
            module.module,
            action_name,
            "binary must be first command element",
        )

    first_element = action.command[0]
    if not isinstance(first_element, BinaryCmd):
        _raise_action_error(
            module.module,
            action_name,
            "binary must be first command element",
        )

    if first_element.binary not in module.binaries:
        _raise_action_error(
            module.module,
            action_name,
            f"binary '{first_element.binary}' is not declared in module binaries",
        )


def _validate_command_elements(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate the types and literal values of command elements.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If a command element is unsupported or an
                    inline string literal is unsafe.
    """

    for element in action.command:
        if isinstance(element, str):
            _validate_command_literal(module_name, action_name, element)
            continue

        if isinstance(element, (BinaryCmd, ArgCmd, FlagCmd)):
            continue

        _raise_action_error(
            module_name,
            action_name,
            "command contains an unsupported element type",
        )


def _validate_command_literal(
    module_name: str,
    action_name: str,
    literal: str,
) -> None:
    """Validate one inline string literal inside a command template.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            literal: Literal command token.

    Raises:
            ActionSpecsParseError: If the literal is empty, blank, or contains
                    control characters.
    """

    if literal == "":
        _raise_action_error(
            module_name,
            action_name,
            "command literal must not be empty",
        )

    if literal.strip() == "":
        _raise_action_error(
            module_name,
            action_name,
            "command literal must not be whitespace-only",
        )

    if "\x00" in literal:
        _raise_action_error(
            module_name,
            action_name,
            "command literal must not contain NULL bytes",
        )

    if _contains_control_characters(literal):
        _raise_action_error(
            module_name,
            action_name,
            "command literal must not contain control characters",
        )


def _validate_command_references(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Ensure all command arg/flag references resolve to declared definitions.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If a command references an undefined arg or
                    flag.
    """

    args = action.args or {}
    flags = action.flags or {}

    for element in action.command:
        if isinstance(element, ArgCmd) and element.arg not in args:
            _raise_action_error(
                module_name,
                action_name,
                f"arg '{element.arg}' referenced in command but not defined",
            )

        if isinstance(element, FlagCmd) and element.flag not in flags:
            _raise_action_error(
                module_name,
                action_name,
                f"flag '{element.flag}' referenced in command but not defined",
            )


def _validate_unused_definitions(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Ensure all declared args and flags are used by the command template.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If any declared arg or flag is unused.
    """

    used_args = {
        element.arg for element in action.command if isinstance(element, ArgCmd)
    }
    used_flags = {
        element.flag for element in action.command if isinstance(element, FlagCmd)
    }

    for arg_name in (action.args or {}).keys():
        if arg_name not in used_args:
            _raise_action_error(
                module_name,
                action_name,
                f"arg '{arg_name}' is defined but not used in command",
            )

    for flag_name in (action.flags or {}).keys():
        if flag_name not in used_flags:
            _raise_action_error(
                module_name,
                action_name,
                f"flag '{flag_name}' is defined but not used in command",
            )


def _validate_args(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate semantic rules for all action arguments.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If any argument rule is violated.
    """

    for arg_name, arg_spec in (action.args or {}).items():
        _validate_arg_required_default_rules(
            module_name=module_name,
            action_name=action_name,
            arg_name=arg_name,
            arg_spec=arg_spec,
        )
        _validate_arg_default(module_name, action_name, arg_name, arg_spec)
        _validate_arg_constraints(module_name, action_name, arg_name, arg_spec)


def _validate_arg_required_default_rules(
    module_name: str,
    action_name: str,
    arg_name: str,
    arg_spec: ArgSpec,
) -> None:
    """Validate the relationship between `required` and `default`.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            arg_name: Argument name.
            arg_spec: Argument definition.

    Raises:
            ActionSpecsParseError: If `required` is invalid, if a required arg also
                    defines a default, or if an optional arg omits its default.
    """

    required = arg_spec.required
    has_default = "default" in arg_spec.model_fields_set

    if required and has_default:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' cannot be required and define a default",
        )

    if not required and not has_default:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' must define a default when not required",
        )


def _validate_arg_default(
    module_name: str,
    action_name: str,
    arg_name: str,
    arg_spec: ArgSpec,
) -> None:
    """Validate an argument default against its declared DSL type.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            arg_name: Argument name.
            arg_spec: Argument definition.

    Raises:
            ActionSpecsParseError: If a provided default value is incompatible with
                    the declared parameter type.
    """

    if "default" not in arg_spec.model_fields_set:
        return

    default = arg_spec.default
    param_type = arg_spec.type

    is_valid = False
    if param_type == ParamType.INT:
        is_valid = _is_int_compatible(default)
    elif param_type == ParamType.FLOAT:
        is_valid = _is_float_compatible(default)
    elif param_type == ParamType.BOOL:
        is_valid = type(default) is bool
    elif param_type == ParamType.STRING:
        is_valid = isinstance(default, str)
    elif param_type == ParamType.FILE_ID:
        is_valid = isinstance(default, str) and _is_uuid4(default)

    if not is_valid:
        _raise_action_error(
            module_name,
            action_name,
            f"default for arg '{arg_name}' is incompatible with declared type "
            f"'{param_type.value}'",
        )


def _validate_arg_constraints(
    module_name: str,
    action_name: str,
    arg_name: str,
    arg_spec: ArgSpec,
) -> None:
    """Validate type-specific argument constraint fields.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            arg_name: Argument name.
            arg_spec: Argument definition.

    Raises:
            ActionSpecsParseError: If type-restricted constraints are misused or
                    numeric constraint values are invalid.
    """

    has_min = "min" in arg_spec.model_fields_set
    has_max = "max" in arg_spec.model_fields_set
    has_max_size = "max_size" in arg_spec.model_fields_set

    if arg_spec.type not in {ParamType.INT, ParamType.FLOAT} and (has_min or has_max):
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' defines min/max but type '{arg_spec.type.value}' "
            "is not numeric",
        )

    if arg_spec.type != ParamType.FILE_ID and has_max_size:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' defines max_size but type "
            f"'{arg_spec.type.value}' is not file_id",
        )

    if has_min and arg_spec.min is None:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' min constraint must be a number",
        )

    if has_max and arg_spec.max is None:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' max constraint must be a number",
        )

    if has_max_size and arg_spec.max_size is None:
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' max_size constraint must be an integer",
        )

    if arg_spec.type == ParamType.FILE_ID and has_max_size:
        max_size = arg_spec.max_size
        if max_size is not None and max_size <= 0:
            _raise_action_error(
                module_name,
                action_name,
                f"arg '{arg_name}' max_size must be greater than 0",
            )

    if arg_spec.type == ParamType.INT:
        if (
            has_min
            and arg_spec.min is not None
            and not float(arg_spec.min).is_integer()
        ):
            _raise_action_error(
                module_name,
                action_name,
                f"arg '{arg_name}' min must be an integer value",
            )

        if (
            has_max
            and arg_spec.max is not None
            and not float(arg_spec.max).is_integer()
        ):
            _raise_action_error(
                module_name,
                action_name,
                f"arg '{arg_name}' max must be an integer value",
            )

    if (
        has_min
        and has_max
        and arg_spec.min is not None
        and arg_spec.max is not None
        and arg_spec.min > arg_spec.max
    ):
        _raise_action_error(
            module_name,
            action_name,
            f"arg '{arg_name}' has min greater than max",
        )


def _validate_flags(
    module_name: str,
    action_name: str,
    action: ActionSpecInput,
) -> None:
    """Validate semantic rules for all action flags.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            action: Action specification.

    Raises:
            ActionSpecsParseError: If any flag rule is violated.
    """

    for flag_name, flag_spec in (action.flags or {}).items():
        _validate_flag_value(module_name, action_name, flag_name, flag_spec)


def _validate_flag_value(
    module_name: str,
    action_name: str,
    flag_name: str,
    flag_spec: FlagSpec,
) -> None:
    """Validate the literal command value associated with one flag.

    Args:
            module_name: Parent module name.
            action_name: Action name.
            flag_name: Flag name.
            flag_spec: Flag definition.

    Raises:
            ActionSpecsParseError: If the flag literal value is empty or blank.
    """

    if flag_spec.value == "":
        _raise_action_error(
            module_name,
            action_name,
            f"flag '{flag_name}' value must not be empty",
        )

    if flag_spec.value.strip() == "":
        _raise_action_error(
            module_name,
            action_name,
            f"flag '{flag_name}' value must not be whitespace-only",
        )

    if "\x00" in flag_spec.value:
        _raise_action_error(
            module_name,
            action_name,
            f"flag '{flag_name}' value must not contain NULL bytes",
        )

    if _contains_control_characters(flag_spec.value):
        _raise_action_error(
            module_name,
            action_name,
            f"flag '{flag_name}' value must not contain control characters",
        )


def _validate_identifier(
    module_name: str,
    identifier_kind: str,
    identifier_value: str,
    action_name: str | None = None,
) -> None:
    """Validate an identifier against the SEG DSL naming regex.

    Args:
            module_name: Current module name.
            identifier_kind: Human-readable identifier kind such as `module`,
                    `action`, `arg`, or `flag`.
            identifier_value: Identifier value to validate.
            action_name: Optional action context for arg/flag validation.

    Raises:
            ActionSpecsParseError: If the identifier does not match the naming
                    pattern `^[a-z][a-z0-9_]*$`.
    """

    if _NAME_PATTERN.fullmatch(identifier_value):
        return

    message = (
        f"invalid {identifier_kind} name '{identifier_value}'; expected pattern "
        "'^[a-z][a-z0-9_]*$'"
    )
    if action_name is None:
        _raise_module_error(module_name, message)
    else:
        _raise_action_error(module_name, action_name, message)


def _contains_control_characters(value: str) -> bool:
    """Return whether a string contains Unicode control characters.

    Args:
            value: String to inspect.

    Returns:
            True if the string contains any control character, otherwise False.
    """

    return any(unicodedata.category(char).startswith("C") for char in value)


def _is_int_compatible(value: object) -> bool:
    """Return whether a value is valid for an `int` DSL default.

    Args:
            value: Value to inspect.

    Returns:
            True when the value is an `int` or an integer-valued `float`, while
            excluding `bool`.
    """

    return type(value) is int or (type(value) is float and value.is_integer())


def _is_float_compatible(value: object) -> bool:
    """Return whether a value is valid for a `float` DSL default.

    Args:
            value: Value to inspect.

    Returns:
            True when the value is an `int` or `float`, while excluding `bool`.
    """

    return type(value) in {int, float}


def _is_uuid4(value: str) -> bool:
    """Return whether a string is a valid UUID version 4.

    Args:
            value: Candidate UUID string.

    Returns:
            True if the value parses as a UUID v4, otherwise False.
    """

    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4


def _raise_module_error(module_name: str, message: str) -> NoReturn:
    """Raise a module-scoped semantic validation error.

    Args:
            module_name: Module name to include in the error.
            message: Human-readable failure detail.

    Raises:
            ActionSpecsParseError: Always.
    """

    full_message = f"Invalid DSL module '{module_name}': {message}"
    logger.error(full_message)
    raise ActionSpecsParseError(full_message)


def _raise_action_error(module_name: str, action_name: str, message: str) -> NoReturn:
    """Raise an action-scoped semantic validation error.

    Args:
            module_name: Module name to include in the error.
            action_name: Action name to include in the error.
            message: Human-readable failure detail.

    Raises:
            ActionSpecsParseError: Always.
    """

    _raise_module_error(module_name, f"{message} in action '{action_name}'")
