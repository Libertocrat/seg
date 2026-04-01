"""Exception types for SEG DSL specs engine."""


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
