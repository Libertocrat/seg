# src/seg/core/security/paths.py
from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from seg.core.config import get_settings


class PathSecurityError(ValueError):
    pass


logger = logging.getLogger("seg.core.security.paths")


@dataclass(frozen=True)
class ValidatedPath:
    """Result of secure path validation.

    Attributes:
        path: Canonical path under the configured sandbox.
        fd: Optional open file descriptor obtained via `safe_open_no_follow`.
            The caller owns this descriptor and must close it.
    """

    path: Path
    fd: int | None = None


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


def validate_path(
    *,
    user_path: str,
    sandbox_dir: Path | None = None,
    require_exists: bool = True,
    require_regular_file: bool = True,
    open_no_follow: bool = False,
    open_flags: int = os.O_RDONLY,
) -> ValidatedPath:
    """Validate and optionally open a user path under the SEG sandbox.

    This helper centralizes common path safety checks used by handlers:
    - Syntactic validation and sandbox resolution (`resolve_in_sandbox`).
    - Allowed-subdir enforcement and symlink-component rejection.
    - Optional existence checks.
    - Optional secure open with no symlink following on final component.

    When `open_no_follow=True`, the target is opened using
    `safe_open_no_follow`, which ensures the final component is not a
    symlink and is a regular file. In this mode, the returned file
    descriptor is owned by the caller and must be closed by them.

    Args:
        user_path: User-provided path relative to sandbox.
        sandbox_dir: Optional sandbox root. Defaults to configured sandbox dir.
        require_exists: If True, raise `FileNotFoundError` when target is absent.
        require_regular_file: If True, reject non-regular files (only applies
            when `open_no_follow=False`).
        open_no_follow: If True, open target via `safe_open_no_follow` and
            return an owned file descriptor in the result.
        open_flags: Flags passed to secure open when `open_no_follow` is True.

    Returns:
        ValidatedPath: Canonical sandboxed path and optional open descriptor.

    Raises:
        PathSecurityError: On sandbox, symlink, or policy violations.
        FileNotFoundError: If required target is missing.
        OSError: For low-level open/stat errors not mapped as security errors.
    """

    # Resolve sandbox root
    sandbox = (
        sandbox_dir if sandbox_dir is not None else Path(get_settings().seg_sandbox_dir)
    )

    # Resolve and validate the path under sandbox policies
    resolved_path = resolve_in_sandbox(sandbox_dir=sandbox, user_path=user_path)

    # ------------------------------------------------------------------
    # Atomic open mode (mitigates TOCTOU for final component)
    # ------------------------------------------------------------------
    if open_no_follow:
        try:
            fd = safe_open_no_follow(resolved_path, flags=open_flags)
        except FileNotFoundError:
            if require_exists:
                raise
            return ValidatedPath(path=resolved_path, fd=None)

        return ValidatedPath(path=resolved_path, fd=fd)

    # ------------------------------------------------------------------
    # Validation-only mode (no atomic open)
    # ------------------------------------------------------------------
    if not require_exists:
        return ValidatedPath(path=resolved_path, fd=None)

    if not resolved_path.exists():
        raise FileNotFoundError(str(resolved_path))

    # Explicitly reject final-component symlinks before file checks
    if resolved_path.is_symlink():
        raise PathSecurityError("Symlinks are not allowed in path components")

    if require_regular_file and not resolved_path.is_file():
        raise PathSecurityError("Target is not a regular file")

    return ValidatedPath(path=resolved_path, fd=None)
