"""Runtime command renderer for SEG DSL actions.

This module transforms a validated `ActionSpec` plus validated runtime params
into a fully resolved `argv` list for subprocess-safe execution.

The renderer is pure and deterministic: it performs no subprocess calls and no
registry lookups, and only reads file metadata/blob presence when resolving
`file_id` args.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from seg.actions.exceptions import (
    ActionInvalidArgError,
    ActionRuntimeError,
    ActionRuntimeRenderError,
)
from seg.actions.models.core import (
    ActionSpec,
    ArgCmd,
    ArgDef,
    BinaryCmd,
    ConstCmd,
    FlagCmd,
    ParamType,
)
from seg.core.utils.file_storage import get_blob_path, load_file_metadata
from seg.routes.files.schemas import FileMetadata


def render_command(spec: ActionSpec, params: dict[str, Any]) -> list[str]:
    """Render a validated action invocation into a final argv list.

    Pipeline (strict order):
        1. Merge defaults + params.
        2. Reject any resolved value that is None.
        3. Resolve `file_id` args into persisted blob paths + metadata.
        4. Apply type-specific runtime constraints.
        5. Build and return final argv from command_template.

    Args:
        spec: Fully built immutable action runtime specification.
        params: Already-validated params payload for the action.

    Returns:
        Final argv list ready for direct subprocess execution.

    Raises:
        ActionInvalidArgError: If any runtime value is invalid.
        ActionRuntimeRenderError: If rendering fails due to internal errors.
    """

    try:
        resolved: dict[str, Any] = {**spec.defaults, **params}

        for name, value in resolved.items():
            if value is None:
                raise ActionInvalidArgError(f"Param '{name}' cannot be None")

        file_metadata_by_arg: dict[str, FileMetadata] = {}

        for name, arg_def in spec.arg_defs.items():
            value = resolved[name]

            if arg_def.type == ParamType.FILE_ID:
                file_uuid = _coerce_file_id(name, value)
                blob_path, metadata = _resolve_file_id_to_path(file_uuid, arg_def)
                resolved[name] = blob_path
                file_metadata_by_arg[name] = metadata

        for name, arg_def in spec.arg_defs.items():
            file_meta: FileMetadata | None = file_metadata_by_arg.get(name)
            _validate_arg(name, resolved[name], arg_def, file_meta)

        argv: list[str] = []
        for token in spec.command_template:
            kind = token["kind"]

            if kind == "binary":
                binary_token = cast(BinaryCmd, token)
                argv.append(binary_token["value"])
                continue

            if kind == "const":
                const_token = cast(ConstCmd, token)
                argv.append(const_token["value"])
                continue

            if kind == "arg":
                arg_token = cast(ArgCmd, token)
                name = arg_token["name"]
                argv.append(str(resolved[name]))
                continue

            if kind == "flag":
                flag_token = cast(FlagCmd, token)
                name = flag_token["name"]
                if resolved[name] is True:
                    argv.append(spec.flag_defs[name].value)
                continue

            raise ActionRuntimeRenderError(f"Unsupported command token kind: {kind}")

        return argv

    except ActionRuntimeError:
        raise
    except Exception as exc:
        raise ActionRuntimeRenderError(
            "Unexpected failure while rendering command"
        ) from exc


def _resolve_file_id_to_path(
    file_id: UUID,
    arg_def: ArgDef,
) -> tuple[str, FileMetadata]:
    """Resolve a `file_id` argument into blob path and loaded metadata.

    Args:
        file_id: File UUID to resolve.
        arg_def: Runtime argument definition for the file parameter.

    Returns:
        Tuple of `(blob_path_str, metadata)`.

    Raises:
        ActionInvalidArgError: If metadata or blob file does not exist.
    """

    _ = arg_def

    metadata = load_file_metadata(file_id)
    if metadata is None:
        raise ActionInvalidArgError(f"File '{file_id}' was not found")

    blob_path = get_blob_path(file_id)
    if not blob_path.exists():
        raise ActionInvalidArgError(f"File blob for '{file_id}' was not found")

    return str(blob_path), metadata


def _validate_arg(
    name: str,
    value: Any,
    arg_def: ArgDef,
    metadata: FileMetadata | None,
) -> None:
    """Apply type-specific runtime constraints to a resolved argument.

    Args:
        name: Argument name.
        value: Resolved runtime value (file_id already converted to path).
        arg_def: Argument definition with declared type/constraints.
        metadata: Pre-loaded file metadata for file_id args; otherwise None.

    Raises:
        ActionInvalidArgError: If validation fails.
    """

    constraints = arg_def.constraints or {}

    if arg_def.type in (ParamType.INT, ParamType.FLOAT):
        _validate_numeric_constraints(name, value, constraints)
        return

    if arg_def.type == ParamType.STRING:
        _validate_string_constraints(name, value, constraints)
        return

    if arg_def.type == ParamType.FILE_ID:
        _validate_file_constraints(name, metadata, constraints)
        return

    if arg_def.type == ParamType.LIST:
        _validate_list_constraints(name, value, constraints)
        return


def _validate_numeric_constraints(
    name: str,
    value: Any,
    constraints: dict[str, Any],
) -> None:
    """Validate numeric bounds for int/float arguments.

    Args:
        name: Argument name.
        value: Runtime numeric value.
        arg_def: Numeric argument definition.

    Raises:
        ActionInvalidArgError: If value is not numeric or outside constraints.
    """

    min_value = constraints.get("min")
    max_value = constraints.get("max")

    if type(value) not in {int, float}:
        raise ActionInvalidArgError(f"Param '{name}' must be numeric")

    if min_value is not None and value < min_value:
        raise ActionInvalidArgError(
            f"Param '{name}' must be greater than or equal to {min_value}"
        )

    if max_value is not None and value > max_value:
        raise ActionInvalidArgError(
            f"Param '{name}' must be less than or equal to {max_value}"
        )


def _validate_string_constraints(
    name: str,
    value: Any,
    constraints: dict[str, Any],
) -> None:
    """Validate runtime string constraints.

    Args:
        name: Argument name.
        value: Runtime string value.

    Raises:
        ActionInvalidArgError: If value is empty/whitespace or flag-like.
    """

    if not isinstance(value, str):
        raise ActionInvalidArgError(f"Param '{name}' must be a string")

    stripped = value.strip()

    if stripped == "":
        raise ActionInvalidArgError(f"Param '{name}' cannot be empty")

    if stripped.startswith("-"):
        raise ActionInvalidArgError(
            f"Param '{name}' cannot start with '-' to avoid flag injection"
        )

    min_length = constraints.get("min_length")
    max_length = constraints.get("max_length")
    allowed_values = constraints.get("allowed_values")

    if min_length is not None and len(value) < min_length:
        raise ActionInvalidArgError(f"Param '{name}' must have length >= {min_length}")

    if max_length is not None and len(value) > max_length:
        raise ActionInvalidArgError(f"Param '{name}' must have length <= {max_length}")

    if allowed_values is not None and value not in allowed_values:
        raise ActionInvalidArgError(
            f"Param '{name}' must be one of: "
            f"{', '.join(str(item) for item in allowed_values)}"
        )


def _validate_file_constraints(
    name: str,
    metadata: FileMetadata | None,
    constraints: dict[str, Any],
) -> None:
    """Validate resolved file constraints using preloaded metadata.

    Args:
        name: Argument name.
        metadata: Loaded file metadata.
        arg_def: File argument definition.

    Raises:
        ActionInvalidArgError: If metadata is missing or max_size exceeded.
    """

    if metadata is None:
        raise ActionInvalidArgError(f"Param '{name}' could not resolve file metadata")

    max_size = constraints.get("max_size")
    allowed_extensions = constraints.get("allowed_extensions")
    allowed_mime_types = constraints.get("allowed_mime_types")

    if max_size is not None and metadata.size_bytes > max_size:
        raise ActionInvalidArgError(
            f"Param '{name}' file size must be <= {max_size} bytes"
        )

    if allowed_extensions is not None:
        normalized_extension = metadata.extension.lower().lstrip(".")
        allowed = {extension.lower().lstrip(".") for extension in allowed_extensions}
        if normalized_extension not in allowed:
            raise ActionInvalidArgError(
                f"Param '{name}' extension '{metadata.extension}' is not allowed"
            )

    if allowed_mime_types is not None:
        normalized_mime = metadata.mime_type.lower()
        allowed = {mime_type.lower() for mime_type in allowed_mime_types}
        if normalized_mime not in allowed:
            raise ActionInvalidArgError(
                f"Param '{name}' mime type '{metadata.mime_type}' is not allowed"
            )


def _validate_list_constraints(
    name: str,
    value: Any,
    constraints: dict[str, Any],
) -> None:
    """Validate runtime list constraints.

    Args:
        name: Argument name.
        value: Runtime value.
        constraints: Declared list constraints.

    Raises:
        ActionInvalidArgError: If list validation fails.
    """

    if not isinstance(value, list):
        raise ActionInvalidArgError(f"Param '{name}' must be a list")

    min_items = constraints.get("min_items")
    max_items = constraints.get("max_items")

    if min_items is not None and len(value) < min_items:
        raise ActionInvalidArgError(
            f"Param '{name}' must contain at least {min_items} item(s)"
        )

    if max_items is not None and len(value) > max_items:
        raise ActionInvalidArgError(
            f"Param '{name}' must contain at most {max_items} item(s)"
        )


def _coerce_file_id(name: str, value: Any) -> UUID:
    """Convert an incoming runtime value into UUID for file_id resolution.

    Args:
        name: Argument name.
        value: Runtime value expected to identify a file.

    Returns:
        Parsed UUID value.

    Raises:
        ActionInvalidArgError: If value cannot be interpreted as UUID.
    """

    if isinstance(value, UUID):
        return value

    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ActionInvalidArgError(f"Param '{name}' must be a valid file_id") from exc
