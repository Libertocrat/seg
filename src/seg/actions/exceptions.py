"""Exception types for SEG DSL build engine."""


class ActionSpecsParseError(Exception):
    """Raised when a DSL spec file cannot be loaded, parsed, or validated.

    This includes:
    - file I/O errors
    - YAML syntax errors
    - schema validation errors (Pydantic)
    - semantic validation errors (validator.py)
    """


class ActionSpecsBuildError(Exception):
    """Raised when validated DSL specs cannot be compiled into `ActionSpec`."""


class ActionRuntimeError(Exception):
    """Base class for SEG action runtime-layer errors."""


class ActionInvalidArgError(ActionRuntimeError):
    """Raised when a user-provided runtime parameter is invalid."""


class ActionRuntimeRenderError(ActionRuntimeError):
    """Raised when runtime command rendering fails unexpectedly."""
