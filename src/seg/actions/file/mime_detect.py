"""Safe, sandboxed MIME detection action implementation.

This module provides the `file_mime_detect` handler used to determine
the MIME type of a file contained under the configured SEG sandbox
directory using libmagic (content-based detection).

Security and behavior notes:
- Validates and resolves the client-supplied relative path under SEG_SANDBOX_DIR,
  ensuring the resolved target is contained in the configured
  SEG_ALLOWED_SUBDIRS; rejects symlinks in path components.
- Mitigates TOCTOU for the final component by opening it with
  `safe_open_no_follow()` (O_NOFOLLOW when available).
- Enforces SEG_MAX_BYTES before reading content.
- Performs MIME detection in a blocking thread.
- Maps errors to `SegActionError` with stable error codes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import magic  # python-magic

from seg.actions.dispatcher import SegActionError
from seg.actions.file.schemas import MimeDetectParams, MimeDetectResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.config import get_settings
from seg.core.security.paths import (
    PathSecurityError,
    resolve_in_sandbox,
    safe_open_no_follow,
)

logger = logging.getLogger("seg.actions.file.mime_detect")


async def file_mime_detect(params: MimeDetectParams) -> MimeDetectResult:
    """Detect MIME type of a file inside the SEG sandbox.

    Args:
        params (MimeDetectParams): Parameters containing a sandbox-relative
            `path` to the file to inspect.

    Returns:
        MimeDetectResult: Result model containing the detected `mime` string.

    Raises:
        SegActionError: On security or runtime errors with one of the
            standardized error codes:
            - PATH_NOT_ALLOWED
            - FILE_NOT_FOUND
            - FILE_TOO_LARGE
            - TIMEOUT
            - INTERNAL_ERROR

    Notes:
        The implementation resolves the user-supplied path under the
        configured sandbox, opens the final component without following
        symlinks, enforces `SEG_MAX_BYTES`, and runs libmagic-based
        detection inside a blocking thread to avoid blocking the event loop.
    """

    sandbox = Path(get_settings().seg_sandbox_dir)

    # Step 1: Resolve path safely
    try:
        path = resolve_in_sandbox(sandbox_dir=sandbox, user_path=params.path)
    except PathSecurityError as exc:
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc

    # Step 2: Open safely (no symlink following)
    try:
        fd = safe_open_no_follow(path)
    except FileNotFoundError as exc:
        raise SegActionError(code="FILE_NOT_FOUND", message="File not found.") from exc
    except PathSecurityError as exc:
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc

    dup_fd: int | None = None

    try:
        # Step 3: Enforce max file size
        st = os.fstat(fd)
        size_bytes = int(st.st_size)

        max_bytes = get_settings().seg_max_bytes
        if max_bytes is not None and size_bytes > max_bytes:
            try:
                os.close(fd)
            except OSError:
                pass
            raise SegActionError(
                code="FILE_TOO_LARGE",
                message="File exceeds maximum allowed size.",
            )

        # Step 4: Duplicate descriptor for blocking thread
        try:
            dup_fd = os.dup(fd)
        except OSError as exc:
            try:
                os.close(fd)
            except Exception as close_exc:
                logger.warning(
                    "Failed to close fd %s during dup-failure cleanup: %s",
                    fd,
                    close_exc,
                )
            logger.exception("Failed to duplicate file descriptor for %s", path)
            raise SegActionError(
                code="INTERNAL_ERROR",
                message="Failed to duplicate file descriptor",
            ) from exc

        async def _detect() -> str:
            def _blocking_detect(fd_inner: int) -> str:
                # Wrap duplicated fd; closes automatically
                with os.fdopen(fd_inner, "rb") as f:
                    try:
                        # Use content-based detection
                        m = magic.Magic(mime=True)
                        return m.from_buffer(f.read(8192))
                    except Exception as exc:
                        raise SegActionError(
                            code="INTERNAL_ERROR",
                            message="MIME detection failed.",
                        ) from exc

            return await asyncio.to_thread(_blocking_detect, dup_fd)

        # Be defensive: `seg_timeout_ms` may be None or invalid in some
        # environments. Use a small non-zero default and coerce to float.
        timeout_ms = get_settings().seg_timeout_ms
        if timeout_ms is None:
            timeout_s = 0.1
        else:
            try:
                timeout_s = max(0.1, float(timeout_ms) / 1000.0)
            except Exception:
                # Fall back to a small non-zero timeout on invalid config.
                timeout_s = 0.1

        try:
            mime_value = await asyncio.wait_for(_detect(), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise SegActionError(
                code="TIMEOUT",
                message="Operation timed out.",
            ) from exc

        return MimeDetectResult(mime=mime_value)

    finally:
        try:
            os.close(fd)
        except OSError:
            pass


# Register action in explicit allowlist
register_action(
    ActionSpec(
        name="file_mime_detect",
        params_model=MimeDetectParams,
        result_model=MimeDetectResult,
        handler=file_mime_detect,
    )
)
