"""
Core domain models for SEG actions.

This module defines the canonical in-memory representation of actions
(`ActionSpec`) as used by the registry and dispatcher, along with the typed
supporting structures that describe action inputs and execution behavior.

Design principles:
- ActionSpec is a passive, immutable data structure.
- It contains no execution logic.
- It is produced by the build engine from `.yml` files.
- It is consumed by the dispatcher and runtime execution layer.
- Pydantic is used for external validation (DSL parsing and request params),
  while these dataclasses model the validated internal runtime state.
- Internal structures should remain strongly typed to support mypy, improve
  readability, and reduce runtime errors caused by loosely typed nested dicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, Literal, Optional, Tuple, Type, TypedDict, Union
from uuid import UUID

from pydantic import BaseModel

# ===========================================================================
# ParamType
# ===========================================================================


class ParamType(str, Enum):
    """Supported logical parameter types for SEG action arguments.

    This enum defines the set of value types currently supported by the
    SEG build engine for action arguments declared in `.yml` files.

    The value of each enum member matches the literal string expected in
    the DSL. The build engine will later map these logical types to the
    appropriate Python or Pydantic runtime types when generating the
    action-specific `params_model`.

    Notes:
        - This enum applies to action arguments, not flags.
        - Flags are modeled separately and always resolve to `bool`.
        - Type-specific constraints are validated later by the build engine.
          For example, `max_size` is valid only for `file_id`.
    """

    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    FILE_ID = "file_id"


# ===========================================================================
# Command template tokens
# ===========================================================================


class BinaryCmd(TypedDict):
    kind: Literal["binary"]
    value: str


class ArgCmd(TypedDict):
    kind: Literal["arg"]
    name: str


class FlagCmd(TypedDict):
    kind: Literal["flag"]
    name: str


class ConstCmd(TypedDict):
    kind: Literal["const"]
    value: str


# Public alias for readability in ActionSpec typing.
CommandElement = Union[BinaryCmd, ArgCmd, FlagCmd, ConstCmd]


# ===========================================================================
# Argument and flag definitions
# ===========================================================================


@dataclass(frozen=True, slots=True)
class ArgDef:
    """Typed internal definition of an action argument.

    ArgDef represents a validated action argument after the `.yml` file has
    been parsed and normalized by the build engine. It is intentionally kept
    generic and lightweight: a single structure is used for all argument types,
    while type-specific rule enforcement is delegated to the specs validator.

    This avoids over-engineering the runtime model with many specialized
    subclasses while still preserving strong typing and clear semantics.

    Attributes:
        type:
            Logical type of the argument as defined by the DSL.

        required:
            Whether the argument must be supplied by the client. If False, the
            argument may still resolve through `default` when one is defined.

        default:
            Optional default value for the argument. The build engine must
            validate that the default is compatible with the declared type.

        min:
            Optional minimum numeric bound. This is intended for numeric types
            such as `int` and `float`. The specs validator must reject it for
            unsupported types.

        max:
            Optional maximum numeric bound. This is intended for numeric types
            such as `int` and `float`. The specs validator must reject it for
            unsupported types.

        max_size:
            Optional maximum allowed file size in bytes. This constraint is
            meaningful only for `file_id` arguments and must be rejected by the
            build validator for any other type.

        description:
            Human-readable description of the argument. This is required in the
            DSL and is used for generated documentation and OpenAPI metadata.
    """

    type: ParamType
    required: bool = False
    default: Any | None = None

    min: float | None = None
    max: float | None = None

    max_size: int | None = None

    description: str = ""


@dataclass(frozen=True, slots=True)
class FlagDef:
    """Typed internal definition of an action flag.

    Flags are boolean runtime inputs that conditionally insert a fixed literal
    value into the final CMD array when enabled. Unlike arguments, flags do not
    carry arbitrary values from the client; they only control presence or
    absence of a predefined command token.

    Attributes:
        value:
            Literal command-line flag to inject when the resolved flag value is
            True (for example, `-b` or `--verbose`).

        default:
            Default boolean value used when the client omits this flag from the
            request params.

        description:
            Human-readable description of the flag. This is required in the DSL
            and is used for generated documentation and OpenAPI metadata.
    """

    value: str
    default: bool
    description: str


# ===========================================================================
# ActionSpec
# ===========================================================================


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """Canonical specification object describing a registered SEG action.

    ActionSpec is the single source of truth for all registered actions in SEG.
    Instances are created at startup by parsing and validating `.yml` spec
    files, then transforming the validated external DSL representation into
    this immutable internal runtime model and storing it in the registry.

    It contains:

    - Identity metadata (`name`, `module`, `action`, `version`)
    - Input validation model (`params_model`)
    - Execution definition (`binary`, command template, args, flags, defaults)
    - Documentation metadata (OpenAPI-compatible)

    It does NOT contain execution logic. Execution is handled by a separate
    runtime layer that consumes this specification.

    Conceptual mapping:
        - DSL `args` + `flags` together become runtime `params`
        - `params_model` validates the `params` field of `/v1/execute`
        - `arg_defs` and `flag_defs` describe how those params behave
        - `command_template` describes how to build the final CMD array

    Attributes:
        name:
            Fully qualified action name (for example, `checksum.sha256`).
            This is the canonical action identifier used in the `action` field
            of the `/v1/execute` request body.

        module:
            Module namespace that groups related actions (for example,
            `checksum` or `random_gen`).

        action:
            Action name within the module (for example, `sha256` or `uuid4`).

        version:
            DSL version used by the `.yml` spec that defined this action.
            This refers to the parser/syntax version, not to an action-specific
            business version.

        params_model:
            Dynamically generated Pydantic model used to validate incoming
            request parameters for this action. This model is also used to
            support automatic OpenAPI generation.

        binary:
            Primary executable name used by the action. This must match the
            binary declared by the first token in `command_template`.

        command_template:
            Normalized ordered representation of the command to build at
            runtime. Each token is strongly typed and uses a discriminated
            shape with a `kind` field. Runtime tokens may represent:
                - the selected binary (`kind='binary'`)
                - a dynamic argument (`kind='arg'`)
                - a conditional flag (`kind='flag'`)
                - a fixed literal string (`kind='const'`)

        arg_defs:
            Typed argument definitions keyed by argument name. These originate
            from the DSL `args` section after validation and normalization.

        flag_defs:
            Typed flag definitions keyed by flag name. These originate from the
            DSL `flags` section after validation and normalization.

        defaults:
            Flattened dictionary of default values for all runtime params
            (arguments and flags). Param names must be globally unique within
            an action, so arg/flag name collisions must be rejected during
            setup.

        authors:
            Optional tuple of module authors declared in the `.yml` spec.

        tags:
            Optional tuple of documentation tags associated with the module or
            action. These are useful for OpenAPI grouping and future static docs.

        summary:
            Optional concise title for the action in generated OpenAPI output.
            If not explicitly defined in the spec, the builder may fall back to
            `description`.

        description:
            Detailed human-readable description of the action.

        deprecated:
            Indicates whether the action is deprecated. This is not currently
            populated by the DSL v1 frozen core, but the field is kept for
            forward-compatible documentation support.

        params_example:
            Optional example payload instance compatible with `params_model`.
            This is intended for OpenAPI example generation.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name: str
    module: str
    action: str
    version: int

    # ------------------------------------------------------------------
    # Input schema
    # ------------------------------------------------------------------

    params_model: Type[BaseModel]

    # ------------------------------------------------------------------
    # Execution definition
    # ------------------------------------------------------------------

    binary: str
    command_template: Tuple[CommandElement, ...]

    arg_defs: dict[str, ArgDef]
    flag_defs: dict[str, FlagDef]
    defaults: dict[str, Any]

    # ------------------------------------------------------------------
    # Module metadata
    # ------------------------------------------------------------------

    authors: tuple[str, ...] | None = None
    tags: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Documentation metadata
    # ------------------------------------------------------------------

    summary: Optional[str] = None
    description: Optional[str] = None
    deprecated: bool = False

    params_example: BaseModel | None = None

    # ------------------------------------------------------------------
    # Helpers (read-only, no execution logic)
    # ------------------------------------------------------------------

    @property
    def fqdn(self) -> str:
        """Return the fully qualified action name.

        This property is an alias of `name` and exists only for readability in
        call sites where the fully qualified meaning is more explicit.
        """
        return self.name

    @property
    def has_args(self) -> bool:
        """Return True if the action defines one or more arguments."""
        return bool(self.arg_defs)

    @property
    def has_flags(self) -> bool:
        """Return True if the action defines one or more flags."""
        return bool(self.flag_defs)

    @property
    def has_defaults(self) -> bool:
        """Return True if the action defines any default runtime params."""
        return bool(self.defaults)

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-friendly nested dictionary representation.

        This mirrors the developer ergonomics of Pydantic's `model_dump()` for
        debugging and inspection of compiled runtime `ActionSpec` objects.

        Returns:
            Nested dictionary containing only JSON-serializable primitives,
            lists, and dictionaries.
        """

        raw = {
            "name": self.name,
            "module": self.module,
            "action": self.action,
            "version": self.version,
            "params_model": self.params_model,
            "binary": self.binary,
            "command_template": self.command_template,
            "arg_defs": self.arg_defs,
            "flag_defs": self.flag_defs,
            "defaults": self.defaults,
            "authors": self.authors,
            "tags": self.tags,
            "summary": self.summary,
            "description": self.description,
            "deprecated": self.deprecated,
            "params_example": self.params_example,
        }
        return _to_jsonable(raw)

    def model_dump_json(self, *, indent: int | None = 2) -> str:
        """Return a JSON string representation of this action spec.

        Args:
            indent: Optional JSON indentation level.

        Returns:
            JSON string for debug and diagnostics output.
        """

        return json.dumps(self.model_dump(), indent=indent, sort_keys=False)


def _to_jsonable(value: Any) -> Any:
    """Recursively convert runtime values into JSON-serializable structures.

    Args:
        value: Arbitrary runtime value.

    Returns:
        JSON-friendly representation of `value`.
    """

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, type) and issubclass(value, BaseModel):
        return {
            "name": value.__name__,
            "schema": value.model_json_schema(),
        }

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]

    return value


# ===========================================================================
# ActionExecutionResult
# ===========================================================================


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    """Execution result returned by the SEG runtime executor.

    Attributes:
        returncode: Process exit code returned by the OS.
        stdout: Raw stdout bytes captured from the process.
        stderr: Raw stderr bytes captured from the process.
        exec_time: Total wall-clock execution time in seconds.
        pid: OS process identifier, or None if process never started.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    exec_time: float
    pid: int | None = None
