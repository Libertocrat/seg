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

import magic  # python-magic

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import MimeDetectParams, MimeDetectResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.config import get_settings
from seg.core.errors import (
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    PATH_NOT_ALLOWED,
    TIMEOUT,
)
from seg.core.security.file_access import secure_file_open_readonly
from seg.core.security.paths import PathSecurityError

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

    # Step 1: Resolve path safely and open without symlink following
    fd: int | None = None
    try:
        validated = secure_file_open_readonly(params.path)
        path = validated.path
        fd = validated.fd
        assert fd is not None
    except PathSecurityError as exc:
        raise SegActionError(PATH_NOT_ALLOWED, str(exc)) from exc
    except FileNotFoundError as exc:
        raise SegActionError(FILE_NOT_FOUND) from exc

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
                FILE_TOO_LARGE,
                "File exceeds maximum allowed size.",
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
                INTERNAL_ERROR,
                "Failed to duplicate file descriptor",
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
                            INTERNAL_ERROR,
                            "MIME detection failed.",
                        ) from exc

            return await asyncio.to_thread(_blocking_detect, dup_fd)

        # Defensive protection: `seg_timeout_ms` may be None or invalid in some
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
                TIMEOUT,
                "Operation timed out.",
            ) from exc

        return MimeDetectResult(mime=mime_value)

    finally:
        if fd is not None:
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
