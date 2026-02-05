# src/seg/actions/file/checksum.py
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from ...core.config import settings
from ...core.security.paths import PathSecurityError, safe_open_no_follow


class FileTooLargeError(ValueError):
    pass


class FileNotFoundErrorSafe(ValueError):
    pass


async def sha256_file(path: Path) -> tuple[str, int]:
    """
    Compute SHA-256 streaming by chunks.

    Returns: (hex_digest, size_bytes)
    """
    # Open the file without following the final symlink to avoid symlink
    # based attacks. `safe_open_no_follow` will perform an O_NOFOLLOW open on
    # POSIX platforms and return a file descriptor.
    try:
        fd = safe_open_no_follow(path)
    except FileNotFoundError as exc:
        raise FileNotFoundErrorSafe("File not found") from exc
    except PathSecurityError as exc:
        # Treat security-related failures as not-found at this layer so the
        # route can surface a PATH_NOT_ALLOWED/403 or FILE_NOT_FOUND consistently.
        raise FileNotFoundErrorSafe("File not accessible") from exc

    try:
        st = os.fstat(fd)
        size_bytes = int(st.st_size)
        if settings.seg_max_bytes is not None and size_bytes > settings.seg_max_bytes:
            try:
                os.close(fd)
            except OSError:
                pass
            raise FileTooLargeError("File exceeds SEG_MAX_BYTES")

        # Read and hash in a blocking thread to avoid blocking the event loop.
        async def _compute() -> str:
            def _blocking_hash(fd_inner: int) -> str:
                h = hashlib.sha256()
                # Wrap fd in a file object; this closes fd when done.
                with os.fdopen(fd_inner, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
                return h.hexdigest()

            return await asyncio.to_thread(_blocking_hash, fd)

        timeout_s = max(0.1, settings.seg_timeout_ms / 1000.0)
        digest = await asyncio.wait_for(_compute(), timeout=timeout_s)
        return digest, size_bytes
    finally:
        # If fd remains open (for example, if fdopen wasn't reached due to
        # an earlier exception), ensure it's closed. If fdopen already closed
        # it, this may raise OSError which we ignore.
        try:
            os.close(fd)
        except OSError:
            pass
