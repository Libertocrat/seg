"""Safe, sandboxed checksum action implementation.

This module provides the `file_checksum` handler used to compute a streaming
checksum of a file contained under the configured SEG sandbox directory.

Security and behavior notes:
- Validates and resolves the client-supplied relative path under SEG_SANDBOX_DIR,
  ensuring the resolved target is also contained in the configured
  SEG_ALLOWED_SUBDIRS; rejects symlinks in path components.
- Mitigates TOCTOU for the final component by opening it with
  `safe_open_no_follow()` (O_NOFOLLOW when available) and performing an fstat
  on the returned descriptor.
- Computes the digest in a blocking thread using a duplicated file descriptor
  so the coroutine may close its descriptor (for example on timeout) without
  interfering with the worker.
- Maps errors to `SegActionError` with stable error codes for dispatcher-level
  handling.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os

from seg.actions.exceptions import SegActionError
from seg.actions.file.schemas import ChecksumParams, ChecksumResult
from seg.actions.registry import ActionSpec, register_action
from seg.core.config import get_settings
from seg.core.errors import (
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    INVALID_ALGORITHM,
    PATH_NOT_ALLOWED,
    TIMEOUT,
)
from seg.core.security.file_access import secure_file_open_readonly
from seg.core.security.paths import PathSecurityError

logger = logging.getLogger("seg.actions.file.checksum")


async def file_checksum(params: ChecksumParams) -> ChecksumResult:
    """Compute a streaming checksum of a file inside the SEG sandbox.

    The function performs a safe, sandboxed checksum while minimizing TOCTOU
    windows and enforcing configured limits.

    Steps:
    1. Resolve `params.path` under the configured sandbox using
        `resolve_in_sandbox` (enforces allowed subdirectories and rejects
        symlinks in path components).
    2. Open the final component with `safe_open_no_follow()` so the final
        path component is not followed if it is a symlink.
    3. Perform an `fstat` on the opened descriptor to obtain the file size and
        enforce `SEG_MAX_BYTES`.
    4. Duplicate the descriptor with `os.dup()` and compute the digest in a
        blocking thread. The duplicated descriptor is closed by the worker
        thread when finished; the coroutine always closes its original fd.

    Args:
        params (ChecksumParams): Action parameters containing:
            - path: relative path under SEG_SANDBOX_DIR
            - algorithm: hashing algorithm (e.g. "sha256")

    Returns:
        ChecksumResult: Object with `algorithm`, `checksum`, and `size_bytes`.

    Raises:
        SegActionError: Raised with one of the stable error codes:
            - PATH_NOT_ALLOWED: path resolution or symlink policy violation.
            - FILE_NOT_FOUND: target does not exist.
            - FILE_TOO_LARGE: file exceeds configured SEG_MAX_BYTES.
            - INVALID_ALGORITHM: provided hashing algorithm is unsupported.
            - TIMEOUT: operation timed out.
            - INTERNAL_ERROR: other internal OS or IO failures.
    """

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

    # Duplicate descriptor to hand off to the blocking thread later. We
    # intentionally *do not* close the duplicated fd in this coroutine if
    # the thread is running; the thread is responsible for closing its dup.
    dup_fd: int | None = None

    try:
        st = os.fstat(fd)
        size_bytes = int(st.st_size)
        if (
            get_settings().seg_max_bytes is not None
            and size_bytes > get_settings().seg_max_bytes
        ):
            try:
                os.close(fd)
            except OSError:
                pass
            raise SegActionError(
                FILE_TOO_LARGE,
                "File exceeds maximum allowed size.",
            )
        # Compute digest in a blocking thread. Duplicate the fd first so the
        # thread owns a separate descriptor and closing `fd` here (for example
        # on timeout) won't affect the thread's read operations.
        algo = params.algorithm

        try:
            dup_fd = os.dup(fd)
        except OSError as exc:
            # Failed to duplicate the fd: close original, log, and surface
            # an internal error
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

        async def _compute() -> str:
            def _blocking_hash(fd_inner: int) -> str:
                try:
                    h = hashlib.new(algo)
                except ValueError as exc:
                    raise SegActionError(
                        INVALID_ALGORITHM,
                        str(exc),
                    ) from exc
                # Wrap duplicated fd in a file object; this closes dup_fd when done.
                with os.fdopen(fd_inner, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
                return h.hexdigest()

            return await asyncio.to_thread(_blocking_hash, dup_fd)

        # Defensive protection: `seg_timeout_ms` may be None or invalid in some
        # environments. Use a small non-zero default and coerce to float.
        timeout_ms = get_settings().seg_timeout_ms
        if timeout_ms is None:
            timeout_s = 0.1
        else:
            try:
                timeout_s = max(0.1, float(timeout_ms) / 1000.0)
            except Exception:
                timeout_s = 0.1
        try:
            digest = await asyncio.wait_for(_compute(), timeout=timeout_s)
        except SegActionError:
            # Propagate algorithm error raised from blocking thread
            raise
        except asyncio.TimeoutError as exc:
            raise SegActionError(
                TIMEOUT,
                "Operation timed out.",
            ) from exc

        return ChecksumResult(algorithm=algo, checksum=digest, size_bytes=size_bytes)
    finally:
        # Always close the original fd owned by this coroutine. The duplicated
        # fd (`dup_fd`) is closed by the worker thread when it finishes; do not
        # attempt to close it here as that would race with the worker.
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


# Register the action in the explicit allowlist.
register_action(
    ActionSpec(
        name="file_checksum",
        params_model=ChecksumParams,
        result_model=ChecksumResult,
        handler=file_checksum,
    )
)
