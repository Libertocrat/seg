import os

from seg.core.security.paths import ValidatedPath, validate_path


def secure_file_open_readonly(user_path: str) -> ValidatedPath:
    """Open a sandboxed file for secure read-only access.

    - Enforces existence.
    - Enforces regular file.
    - Uses atomic open with no symlink following.
    """
    validated = validate_path(
        user_path=user_path,
        require_exists=True,
        require_regular_file=True,
        open_no_follow=True,
        open_flags=os.O_RDONLY,
    )
    return validated


def secure_file_validate_only(user_path: str) -> ValidatedPath:
    """Validate a sandboxed file path without opening it.

    - Enforces existence.
    - Enforces regular file.

    Returns a `ValidatedPath` with `fd=None`.
    """
    validated = validate_path(
        user_path=user_path,
        require_exists=True,
        require_regular_file=True,
        open_no_follow=False,
    )
    return validated
