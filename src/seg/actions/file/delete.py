"""Secure `file_delete` action implementation.

This module provides the `file_delete` handler used by the dispatcher to
safely remove regular files inside the configured SEG sandbox directory.

Key guarantees:
- Syntactic validation and resolution under SEG_SANDBOX_DIR and SEG_ALLOWED_SUBDIRS.
- Mitigates TOCTOU for the final component using `safe_open_no_follow`.
- Rejects symbolic links and non-regular files.
- Maps failures to `SegActionError` with stable error codes
  (e.g. PATH_NOT_ALLOWED, FILE_NOT_FOUND, PERMISSION_DENIED, INTERNAL_ERROR).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import DeleteParams, DeleteResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.errors import (
    FILE_NOT_FOUND,
    INTERNAL_ERROR,
    PATH_NOT_ALLOWED,
    PERMISSION_DENIED,
)
from seg.core.security.file_access import secure_file_open_readonly
from seg.core.security.paths import (
    PathSecurityError,
    validate_path,
)

logger = logging.getLogger("seg.actions.file.delete")


async def file_delete(params: DeleteParams) -> DeleteResult:
    """Safely delete a file inside the SEG sandbox.

    Performs deletion while minimizing TOCTOU windows and enforcing sandbox
    policies (no symlinks, regular file only, allowed subdirectories).

    Steps:
      1. Resolve `params.path` under the configured sandbox using
         `resolve_in_sandbox`.
      2. Atomically validate the final path component with
         `safe_open_no_follow()` to ensure it exists and is a regular file
         without following symlinks.
      3. Close the validated descriptor and call `os.unlink()` to remove the file.
         Handle races where the file may disappear between validation and unlink.

    Args:
        params (DeleteParams): Action parameters.
            - path: relative path under SEG_SANDBOX_DIR to delete.
            - require_exists: if True, missing target results in FILE_NOT_FOUND;
              if False, the operation is idempotent and returns deleted=False.

    Returns:
        DeleteResult: Contains `deleted` (bool) indicating whether deletion
        actually occurred.

    Raises:
        SegActionError: Raised with one of the stable error codes:
            - PATH_NOT_ALLOWED: path is invalid, outside root, or contains symlinks.
            - FILE_NOT_FOUND: target missing and `require_exists` is True.
            - PERMISSION_DENIED: insufficient permissions to delete the target.
            - INTERNAL_ERROR: internal inspection or unlink failure.
    """
    try:
        if params.require_exists:
            validated = secure_file_open_readonly(params.path)
        else:
            # preserve semantics when caller allows missing targets
            validated = validate_path(
                user_path=params.path,
                open_no_follow=True,
                require_exists=False,
                require_regular_file=True,
            )
    except PathSecurityError as exc:
        raise SegActionError(PATH_NOT_ALLOWED, str(exc)) from exc
    except FileNotFoundError as exc:
        if params.require_exists:
            raise SegActionError(FILE_NOT_FOUND) from exc
        return DeleteResult(deleted=False)

    # Ensure target is a Path object
    target_path: Path = validated.path

    # Validate final component to safely close TOCTOU window.
    # The returned fd is owned by this coroutine and must be closed;
    fd: int | None = validated.fd
    if fd is None:
        # Missing target with require_exists=False is idempotent
        return DeleteResult(deleted=False)

    try:
        # Close fd owned by this coroutine; safe_open_no_follow validated the file.
        os.close(fd)
    except OSError:
        pass

    # Attempt to unlink/delete the file
    try:
        os.unlink(str(target_path))
    except FileNotFoundError as exc:
        # Race: file disappeared after validation
        if params.require_exists:
            raise SegActionError(FILE_NOT_FOUND) from exc
        return DeleteResult(deleted=False)
    except PermissionError as exc:
        logger.exception("Permission denied when deleting %s", target_path)
        raise SegActionError(
            PERMISSION_DENIED,
            "Permission denied while deleting target",
        ) from exc
    except OSError as exc:
        logger.exception("Failed to delete %s", target_path)
        raise SegActionError(INTERNAL_ERROR, "Failed to delete target") from exc

    return DeleteResult(deleted=True)


# Register the action
register_action(
    ActionSpec(
        name="file_delete",
        params_model=DeleteParams,
        result_model=DeleteResult,
        handler=file_delete,
    )
)
