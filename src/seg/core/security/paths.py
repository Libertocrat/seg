# src/seg/core/security/paths.py
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from seg.core.config import get_settings


class PathSecurityError(ValueError):
    pass


logger = logging.getLogger("seg.core.security.paths")


def sanitize_rel_path(user_path: str) -> str:
    """Syntactically validate and normalize a user-supplied relative path.

    This performs only syntactic checks: NULs, backslashes, control
    characters, absolute paths, traversal (`..`), and a maximum length.
    It does NOT perform filesystem checks (symlink detection or whether the
    resolved path is within a sandbox). Callers must combine this with
    `resolve_in_sandbox` or `safe_open_no_follow` for filesystem-safe
    operations.
    """

    if "\x00" in user_path:
        raise PathSecurityError("NUL byte not allowed in path")
    # reject Windows-style separators
    if "\\" in user_path:
        raise PathSecurityError("Backslashes not allowed in path")
    p = user_path.strip()

    # reject control characters
    if any(ord(c) < 32 for c in p):
        raise PathSecurityError("Control characters are not allowed in path")

    # enforce reasonable maximum length to avoid DoS via huge paths
    MAX_PATH_LEN = 4096
    if len(p) > MAX_PATH_LEN:
        raise PathSecurityError("Path length exceeds maximum")

    if p == "":
        raise PathSecurityError("Empty path")

    # reject absolute paths
    if p.startswith("/"):
        raise PathSecurityError("Absolute paths are not allowed")

    # reject traversal
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise PathSecurityError("Path traversal '..' is not allowed")

    return "/".join(parts)


def resolve_in_sandbox(sandbox_dir: Path, user_path: str) -> Path:
    """Resolve a user-supplied relative path under a configured sandbox.

    This helper validates the relative path syntactically and ensures the
    resulting normalized path stays under `sandbox_dir`. Note: resolving a Path
    and later opening it in a separate operation can introduce a
    TOCTOU (time-of-check/time-of-use) window. For sensitive operations,
    prefer opening the path atomically via `safe_open_no_follow` or an
    open-at traversal helper.
    """
    rel = sanitize_rel_path(user_path)

    # Enforce allowlist (first component) if configured
    allowed = get_settings().allowed_subdirs
    if allowed and allowed != ["*"]:
        first = rel.split("/", 1)[0]
        if first not in allowed:
            raise PathSecurityError("Path not inside allowed subdirectories")

    # Ensure sandbox exists and is canonical
    try:
        sandbox_resolved = sandbox_dir.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathSecurityError("Configured sandbox dir does not exist") from exc

    # Reject symlinks in any existing path component under sandbox
    cur = sandbox_resolved
    for part in rel.split("/"):
        candidate_component = cur / part
        if candidate_component.exists() and candidate_component.is_symlink():
            raise PathSecurityError("Symlinks are not allowed in path components")
        cur = candidate_component

    # Construct candidate path without resolving symlinks (normpath on joined strings)
    candidate_str = os.path.normpath(os.path.join(str(sandbox_resolved), rel))
    # Ensure candidate is still within sandbox dir.
    # String-based check avoids following symlinks.
    try:
        common = os.path.commonpath([str(sandbox_resolved), candidate_str])
    except Exception as exc:
        raise PathSecurityError("Path is outside allowed sandbox") from exc

    if common != str(sandbox_resolved):
        raise PathSecurityError("Path is outside allowed sandbox")

    return Path(candidate_str)


def safe_open_no_follow(path: Path, flags: int = os.O_RDONLY):
    """Open `path` without following a final symlink (POSIX `O_NOFOLLOW`).

    This attempts an `O_NOFOLLOW` open so the final path component is not
    followed if it is a symlink. The returned file descriptor must be
    wrapped (for example with `os.fdopen(fd, 'rb')`) and closed by the
    caller. This helper mitigates symlink-following at open time but does
    not eliminate TOCTOU if callers previously resolved path strings and
    then open them later; to avoid that, open the file via this helper as
    close in time to validation.

    Raises:
        - FileNotFoundError: target does not exist
        - PathSecurityError: when the open fails for security-related reasons
    """
    # Add O_NOFOLLOW if available on this platform
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    open_flags = flags | nofollow
    try:
        fd = os.open(str(path), open_flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        # Translate certain errno to a security error
        raise PathSecurityError("Failed to open path safely") from exc

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            try:
                os.close(fd)
            except Exception as close_exc:
                logger.warning(
                    "Failed to close fd %s during cleanup: %s", fd, close_exc
                )
            raise PathSecurityError("Target is not a regular file")
    except Exception:
        # Ensure fd closed on any failure
        try:
            os.close(fd)
        except Exception as close_exc:
            logger.warning("Failed to close fd %s during cleanup: %s", fd, close_exc)
        raise

    return fd
