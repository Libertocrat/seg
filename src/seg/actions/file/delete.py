"""Secure `delete_file` action implementation.

This module provides the `delete_file` handler used by the dispatcher to
safely remove regular files inside the configured SEG filesystem root.

Key guarantees:
- Syntactic validation and resolution under SEG_FS_ROOT and SEG_ALLOWED_SUBDIRS.
- Mitigates TOCTOU for the final component using `safe_open_no_follow`.
- Rejects symbolic links and non-regular files.
- Maps failures to `SegActionError` with stable error codes
  (e.g. PATH_NOT_ALLOWED, FILE_NOT_FOUND, PERMISSION_DENIED, INTERNAL_ERROR).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from seg.actions.dispatcher import SegActionError
from seg.actions.file.schemas import DeleteParams, DeleteResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.config import settings
from seg.core.security.paths import (
    PathSecurityError,
    resolve_under_root,
    safe_open_no_follow,
)

logger = logging.getLogger("seg.actions.file.delete")


async def delete_file(params: DeleteParams) -> DeleteResult:
    """Safely delete a file inside the SEG sandbox.

    Performs deletion while minimizing TOCTOU windows and enforcing sandbox
    policies (no symlinks, regular file only, allowed subdirectories).

    Steps:
      1. Resolve `params.path` under the configured root using
         `resolve_under_root`.
      2. Atomically validate the final path component with
         `safe_open_no_follow()` to ensure it exists and is a regular file
         without following symlinks.
      3. Close the validated descriptor and call `os.unlink()` to remove the file.
         Handle races where the file may disappear between validation and unlink.

    Args:
        params (DeleteParams): Action parameters.
            - path: relative path under SEG_FS_ROOT to delete.
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
    root = Path(settings.seg_fs_root)
    try:
        target = resolve_under_root(root=root, user_path=params.path)
    except PathSecurityError as exc:
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc

    # Ensure target is a Path object
    target_path: Path = target

    # Use safe_open_no_follow to atomically validate final component (no symlink,
    # regular file) similarly to checksum_file.
    fd: int | None = None
    try:
        fd = safe_open_no_follow(target_path)
    except FileNotFoundError as exc:
        # Missing target; respect require_exists
        if params.require_exists:
            raise SegActionError(
                code="FILE_NOT_FOUND", message="File not found."
            ) from exc
        return DeleteResult(deleted=False)
    except PathSecurityError as exc:
        # Includes symlink/fstype rejections from the helper
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc
    except OSError as exc:
        logger.exception("safe_open_no_follow failed for %s", target_path)
        raise SegActionError(
            code="INTERNAL_ERROR", message="Failed to inspect target"
        ) from exc
    finally:
        # Close fd owned by this coroutine; safe_open_no_follow validated the file.
        try:
            if fd is not None:
                os.close(fd)
        except OSError:
            pass

    # Attempt to unlink/delete the file
    try:
        os.unlink(str(target_path))
    except FileNotFoundError as exc:
        # Race: file disappeared after validation
        if params.require_exists:
            raise SegActionError(
                code="FILE_NOT_FOUND", message="File not found."
            ) from exc
        return DeleteResult(deleted=False)
    except PermissionError as exc:
        logger.exception("Permission denied when deleting %s", target_path)
        raise SegActionError(
            code="PERMISSION_DENIED", message="Permission denied while deleting target"
        ) from exc
    except OSError as exc:
        logger.exception("Failed to delete %s", target_path)
        raise SegActionError(
            code="INTERNAL_ERROR", message="Failed to delete target"
        ) from exc

    return DeleteResult(deleted=True)


# Register the action
register_action(
    ActionSpec(
        name="delete_file",
        params_model=DeleteParams,
        result_model=DeleteResult,
        handler=delete_file,
    )
)
