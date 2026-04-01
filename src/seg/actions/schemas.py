"""
Pydantic schemas for SEG DSL (YML-based action definitions).

These models validate the structure of .yml files before being compiled
into ActionSpec objects.

They are used ONLY during startup (definition loading phase).

Design principles:
- These schemas validate *external input* (DSL definitions).
- They are intentionally separate from runtime models (see models.py).
- They enforce structural correctness but not all semantic constraints.
- Deeper validation (type compatibility, cross-field rules) is handled
  by the build engine validator layer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from seg.actions.models import ParamType

# ===========================================================================
# ArgSpec
# ===========================================================================


class ArgSpec(BaseModel):
    """Definition of an argument in the SEG DSL.

    This schema represents the raw argument definition as declared in the
    `.yml` file. It is validated during the specs loading phase and later
    transformed into an internal ArgDef dataclass.

    Attributes:
        type:
            Logical parameter type defined in the DSL. This is validated
            against ParamType and later mapped to Python/Pydantic types.

        required:
            Whether the argument must be explicitly provided by the client.
            Defaults to False.

        default:
            Optional default value. Must be compatible with the declared type.
            Type compatibility is validated later in the specs validator.

        min:
            Optional minimum numeric bound. Applies only to numeric types
            (int, float). Must be validated against the declared type.

        max:
            Optional maximum numeric bound. Applies only to numeric types
            (int, float). Must be validated against the declared type.

        max_size:
            Optional maximum allowed file size in bytes. Only valid for
            arguments of type `file_id`.

        description:
            Human-readable description of the argument. Required for docs.
    """

    type: ParamType
    required: Optional[bool] = False
    default: Optional[Any] = None

    # Numeric constraints
    min: Optional[float] = None
    max: Optional[float] = None

    # file_id-specific constraint
    max_size: Optional[int] = None

    description: str


# ===========================================================================
# FlagSpec
# ===========================================================================


class FlagSpec(BaseModel):
    """Definition of a flag in the SEG DSL.

    Flags represent boolean inputs that conditionally inject a fixed literal
    value into the final command when enabled.

    Attributes:
        value:
            Literal CLI flag to append when True (e.g. "-b", "--verbose").

        default:
            Default boolean value if the flag is not provided by the client.

        description:
            Human-readable description used for documentation.
    """

    value: str
    default: bool
    description: str


# ===========================================================================
# Command Tokens (DSL-level representation)
# ===========================================================================


class BinaryCmd(BaseModel):
    """DSL token representing the selected binary.

    This must appear exactly once and as the first element of the command.
    """

    binary: str


class ArgCmd(BaseModel):
    """DSL token referencing a defined argument."""

    arg: str


class FlagCmd(BaseModel):
    """DSL token referencing a defined flag."""

    flag: str


CommandElement = Union[str, BinaryCmd, ArgCmd, FlagCmd]


# ===========================================================================
# ActionSpecInput (raw DSL action)
# ===========================================================================


class ActionSpecInput(BaseModel):
    """Raw action definition as declared in the DSL.

    This schema validates the structure of each action inside the module
    definition before it is compiled into an ActionSpec.

    Attributes:
        description:
            Required detailed description of the action.

        summary:
            Optional short description. If not provided, it may be derived
            from `description` during the build phase.

        args:
            Optional dictionary of argument definitions.

        flags:
            Optional dictionary of flag definitions.

        command:
            Ordered list defining how to construct the final command.
            Each element must be:
                - a literal string
                - a binary token
                - an arg reference
                - a flag reference
    """

    description: str
    summary: Optional[str] = None

    args: Optional[Dict[str, ArgSpec]] = None
    flags: Optional[Dict[str, FlagSpec]] = None

    command: List[CommandElement]


# ===========================================================================
# ModuleSpec (root DSL structure)
# ===========================================================================


class ModuleSpec(BaseModel):
    """Root DSL module definition.

    This schema represents the entire contents of a `.yml` file describing
    a module and its actions.

    Attributes:
        version:
            DSL version. Must be 1.

        module:
            Module namespace. Used as prefix for action names.

        description:
            Human-readable description of the module.

        authors:
            Optional list of author identifiers.

        tags:
            Optional comma-separated string of tags.

        binaries:
            List of allowed binaries for all actions in this module.

        actions:
            Dictionary mapping action names to their definitions.
    """

    version: int
    module: str
    description: str

    authors: Optional[List[str]] = None
    tags: Optional[str] = None

    binaries: List[str]

    actions: Dict[str, ActionSpecInput]
