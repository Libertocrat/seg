# src/seg/actions/file/checksum.py
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

from ...core.config import settings
from ...core.security.paths import (
    PathSecurityError,
    resolve_under_root,
    safe_open_no_follow,
)
from ..dispatcher import SegActionError
from ..registry import ActionSpec, register_action
from .schemas import ChecksumParams, ChecksumResult

logger = logging.getLogger("seg.actions.file.checksum")


async def checksum_file(params: ChecksumParams) -> ChecksumResult:
    """Handler for the `checksum_file` action.

    This function performs a safe, sandboxed checksum of a file under the
    configured SEG root. Steps and safety considerations:

    1. Resolve the client-supplied relative `path` via `resolve_under_root`
        and enforce allowlists / symlink rules.
    2. Open the target file using `safe_open_no_follow()` which returns a
        raw file descriptor opened with `O_NOFOLLOW` when available.
    3. Perform an `fstat` on the opened descriptor to enforce `seg_max_bytes`.
    4. Duplicate the open descriptor with `os.dup()` and pass the duplicated
        descriptor into a blocking thread that reads the file and computes the
        digest. Duplicating the fd ensures the main coroutine can close its
        descriptor (for example on timeout) without racing with the blocking
        thread which owns the duplicated descriptor.

    Important: do NOT close the duplicated descriptor in the main coroutine
    while the thread may be running; the thread closes its own descriptor
    when finished. This avoids use-after-close races and leaked/invalid FDs.

    The function raises `SegActionError` for well-known failure modes so the
    dispatcher can convert them to stable `ResponseEnvelope` failures.
    """

    # Resolve path safely under configured root.
    root = Path(settings.seg_fs_root)
    try:
        path = resolve_under_root(root=root, user_path=params.path)
    except PathSecurityError as exc:
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc

    # Open file without following symlinks.
    try:
        fd = safe_open_no_follow(path)
    except FileNotFoundError as exc:
        raise SegActionError(code="FILE_NOT_FOUND", message="File not found.") from exc
    except PathSecurityError as exc:
        raise SegActionError(code="PATH_NOT_ALLOWED", message=str(exc)) from exc
    # Duplicate descriptor to hand off to the blocking thread later. We
    # intentionally *do not* close the duplicated fd in this coroutine if
    # the thread is running; the thread is responsible for closing its dup.
    dup_fd: int | None = None

    try:
        st = os.fstat(fd)
        size_bytes = int(st.st_size)
        if settings.seg_max_bytes is not None and size_bytes > settings.seg_max_bytes:
            try:
                os.close(fd)
            except OSError:
                pass
            raise SegActionError(
                code="FILE_TOO_LARGE",
                message="File exceeds maximum allowed size.",
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
                code="INTERNAL_ERROR", message="Failed to duplicate file descriptor"
            ) from exc

        async def _compute() -> str:
            def _blocking_hash(fd_inner: int) -> str:
                try:
                    h = hashlib.new(algo)
                except ValueError as exc:
                    raise SegActionError(
                        code="INVALID_ALGORITHM", message=str(exc)
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

        timeout_s = max(0.1, settings.seg_timeout_ms / 1000.0)
        try:
            digest = await asyncio.wait_for(_compute(), timeout=timeout_s)
        except SegActionError:
            # Propagate algorithm error raised from blocking thread
            raise
        except asyncio.TimeoutError as exc:
            raise SegActionError(
                code="TIMEOUT", message="Operation timed out."
            ) from exc

        return ChecksumResult(algorithm=algo, checksum=digest, size_bytes=size_bytes)
    finally:
        # Always close the original fd owned by this coroutine. The duplicated
        # fd (`dup_fd`) is closed by the worker thread when it finishes; do not
        # attempt to close it here as that would race with the worker.
        try:
            os.close(fd)
        except OSError:
            pass


# Register the action in the explicit allowlist.
register_action(
    ActionSpec(
        name="checksum_file",
        params_model=ChecksumParams,
        result_model=ChecksumResult,
        handler=checksum_file,
    )
)
