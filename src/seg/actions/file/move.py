"""Secure `file_move` action implementation.

This module provides the `file_move` handler used by the dispatcher to
safely move regular files within the configured SEG sandbox directory.

Key guarantees:
- Validates source path under sandbox and rejects symlinks.
- Validates destination path under sandbox and applies overwrite policy.
- Enforces extension-preserving moves.
- Performs atomic replacement using `os.replace`.
- Maps failures to `SegActionError` with stable error codes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import FileMoveParams, FileMoveResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.errors import (
    CONFLICT,
    FILE_NOT_FOUND,
    INTERNAL_ERROR,
    PATH_NOT_ALLOWED,
    PERMISSION_DENIED,
)
from seg.core.security.file_access import (
    secure_file_destination_validate,
    secure_file_open_readonly,
    secure_file_validate_only,
)
from seg.core.security.paths import (
    DestinationExistsError,
    DestinationNotRegularError,
    PathSecurityError,
)

logger = logging.getLogger("seg.actions.file.move")


async def file_move(params: FileMoveParams) -> FileMoveResult:
    """Safely move a file inside the SEG sandbox.

    Args:
            params (FileMoveParams): Parameters with `source_path`,
                    `destination_path`, and `overwrite` flag.

    Returns:
            FileMoveResult: Move outcome including original and destination paths.

    Raises:
            SegActionError: Raised with stable action error codes on security,
                    policy, or operating-system failures.
    """
    source_fd: int | None = None

    # Step 1: Validate source (exists, regular file, no symlink, in sandbox)
    try:
        source_validated = secure_file_open_readonly(params.source_path)
        source_path = source_validated.path
        source_fd = source_validated.fd
        assert source_fd is not None
    except PathSecurityError as exc:
        raise SegActionError(PATH_NOT_ALLOWED, str(exc)) from exc
    except FileNotFoundError as exc:
        raise SegActionError(FILE_NOT_FOUND) from exc
    finally:
        # Close validation descriptor immediately as requested.
        if source_fd is not None:
            try:
                os.close(source_fd)
            except OSError:
                pass

    # Step 2: Enforce extension preservation.
    source_ext = Path(params.source_path).suffix.lower()
    destination_ext = Path(params.destination_path).suffix.lower()

    if source_ext != destination_ext:
        raise SegActionError(CONFLICT, "File extension change is not allowed.")

    # Step 3 + 4: Validate destination and apply overwrite policy.
    try:
        destination_validated = secure_file_destination_validate(
            params.destination_path
        )
        destination_path = destination_validated.path
    except DestinationExistsError as exc:
        if not params.overwrite:
            raise SegActionError(CONFLICT) from exc

        # Destination exists and is a regular file: allowed when overwrite=True.
        destination_path = secure_file_validate_only(params.destination_path).path
    except DestinationNotRegularError as exc:
        raise SegActionError(CONFLICT, str(exc)) from exc
    except PathSecurityError as exc:
        raise SegActionError(PATH_NOT_ALLOWED, str(exc)) from exc

    # Step 5: Perform atomic move with error mapping.
    try:
        os.replace(source_path, destination_path)
    except FileNotFoundError as exc:
        raise SegActionError(FILE_NOT_FOUND) from exc
    except PermissionError as exc:
        logger.exception(
            "Permission denied moving %s to %s",
            source_path,
            destination_path,
        )
        raise SegActionError(PERMISSION_DENIED) from exc
    except OSError as exc:
        logger.exception("Failed moving %s to %s", source_path, destination_path)
        raise SegActionError(INTERNAL_ERROR) from exc

    # Step 6: Return result payload.
    return FileMoveResult(
        moved=True,
        source=params.source_path,
        destination=params.destination_path,
    )


# Step 7: Register action in explicit allowlist.
register_action(
    ActionSpec(
        name="file_move",
        params_model=FileMoveParams,
        result_model=FileMoveResult,
        handler=file_move,
        summary="Move a file within the sandbox",
        description="""
Moves a file between paths inside the SEG sandbox with strict policy enforcement.

This action:

- Validates both source and destination paths
- Enforces sandbox boundaries
- Preserves file extension integrity
- Supports controlled overwrite behavior

Designed for safe internal file lifecycle operations without exposing
raw filesystem primitives.
""",
        tags=("file", "lifecycle", "move"),
        params_example=FileMoveParams(
            source_path="relative/path/to/source.txt",
            destination_path="relative/path/to/destination.txt",
            overwrite=False,
        ),
        result_example=FileMoveResult(
            moved=True,
            source="relative/path/to/source.txt",
            destination="relative/path/to/destination.txt",
        ),
    )
)
