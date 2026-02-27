from __future__ import annotations

import logging
from pathlib import Path

from seg.actions.exceptions import SegActionError
from seg.actions.file.checksum import file_checksum
from seg.actions.file.mime_detect import file_mime_detect
from seg.actions.file.schemas import (
    ChecksumParams,
    FileVerifyParams,
    FileVerifyResult,
    MimeDetectParams,
    VerifyChecksumParams,
)
from seg.actions.registry import ActionSpec, register_action
from seg.core.errors import (
    FILE_EXTENSION_MISSING,
    FILE_NOT_FOUND,
    MIME_MAPPING_NOT_DEFINED,
    PATH_NOT_ALLOWED,
)
from seg.core.security.file_access import secure_file_validate_only
from seg.core.security.mime_map import EXTENSION_MIME_MAP
from seg.core.security.paths import PathSecurityError

logger = logging.getLogger("seg.actions.file.verify")


async def file_verify(params: FileVerifyParams) -> FileVerifyResult:
    """Verify file content, extension and optional checksum.

    This composite action performs content-based MIME detection, compares
    the detected MIME against an expected set (inferred from extension or
    provided explicitly), enforces optional allowed-extension and
    allowed-mime policies, and optionally validates a checksum.

    Args:
        params (FileVerifyParams): Parameters for verification.

    Returns:
        FileVerifyResult: Aggregated verification results.

    Raises:
        SegActionError: On policy or technical errors with stable error codes
            including `FILE_EXTENSION_MISSING` and `MIME_MAPPING_NOT_DEFINED`.
    """

    # ------------------------------------------------------------------
    # Step 0: Validate path once (fail fast with stable security codes)
    # ------------------------------------------------------------------
    try:
        # Use wrapper for validation-only checks; returns ValidatedPath (fd=None)
        secure_file_validate_only(params.path)
    except PathSecurityError as exc:
        raise SegActionError(PATH_NOT_ALLOWED, str(exc)) from exc
    except FileNotFoundError as exc:
        raise SegActionError(FILE_NOT_FOUND) from exc

    # ------------------------------------------------------------------
    # Step 1: Detect MIME (reuses hardened handler)
    # ------------------------------------------------------------------
    mime_result = await file_mime_detect(MimeDetectParams(path=params.path))

    detected_mime = mime_result.mime.strip().lower()

    # ------------------------------------------------------------------
    # Step 2: Extract extension (normalized)
    # ------------------------------------------------------------------
    extension = Path(params.path).suffix.lower().strip()

    # ------------------------------------------------------------------
    # Step 3: Determine expected MIME
    # ------------------------------------------------------------------
    if params.expected_mime:
        expected_mime_set = {params.expected_mime.strip().lower()}
    else:
        if not extension:
            logger.error(
                "file_verify: missing file extension and no expected_mime provided: %s",
                params.path,
            )
            raise SegActionError(
                FILE_EXTENSION_MISSING,
                "Cannot infer MIME type because file has no extension.",
            )

        allowed_mimes_for_extension = EXTENSION_MIME_MAP.get(extension)

        if not allowed_mimes_for_extension:
            logger.error(
                "file_verify: no MIME mapping defined for extension %s (path=%s)",
                extension,
                params.path,
            )
            raise SegActionError(
                MIME_MAPPING_NOT_DEFINED,
                "No MIME mapping defined for file extension.",
                details={"extension": extension},
            )

        expected_mime_set = {m.lower() for m in allowed_mimes_for_extension}

    mime_matches = detected_mime in expected_mime_set

    # ------------------------------------------------------------------
    # Step 4: Allowed MIME policy (optional)
    # ------------------------------------------------------------------
    if params.allowed_mime_types is not None:
        allowed_mime_set = {m.strip().lower() for m in params.allowed_mime_types}
        mime_allowed = detected_mime in allowed_mime_set
    else:
        mime_allowed = True

    # ------------------------------------------------------------------
    # Step 5: Allowed extension policy (optional)
    # ------------------------------------------------------------------
    if params.allowed_extensions is not None:
        allowed_ext_set = {
            (
                e.strip().lower()
                if e.strip().startswith(".")
                else f".{e.strip().lower()}"
            )
            for e in params.allowed_extensions
        }
        extension_allowed = extension in allowed_ext_set
    else:
        extension_allowed = True

    # ------------------------------------------------------------------
    # Step 6: Optional checksum validation
    # ------------------------------------------------------------------
    checksum_matches: bool | None = None
    size_bytes: int

    if params.checksum is not None:
        checksum_result = await file_checksum(
            ChecksumParams(
                path=params.path,
                algorithm=params.checksum.algorithm,
            )
        )

        size_bytes = checksum_result.size_bytes

        checksum_matches = (
            checksum_result.checksum.lower() == params.checksum.expected.lower()
        )
    else:
        # We still need size_bytes even if checksum not requested.
        # Reuse checksum handler to get size safely.
        checksum_result = await file_checksum(
            ChecksumParams(path=params.path, algorithm="sha256")
        )
        size_bytes = checksum_result.size_bytes
        checksum_matches = None

    # ------------------------------------------------------------------
    # Step 7: Final policy evaluation
    # ------------------------------------------------------------------
    file_verified = (
        mime_matches
        and mime_allowed
        and extension_allowed
        and (checksum_matches if checksum_matches is not None else True)
    )

    return FileVerifyResult(
        file_verified=file_verified,
        size_bytes=size_bytes,
        detected_mime=detected_mime,
        extension=extension,
        mime_matches=mime_matches,
        extension_allowed=extension_allowed,
        mime_allowed=mime_allowed,
        checksum_matches=checksum_matches,
    )


# Register action in explicit allowlist
register_action(
    ActionSpec(
        name="file_verify",
        params_model=FileVerifyParams,
        result_model=FileVerifyResult,
        handler=file_verify,
        summary="Verify file type and optional checksum",
        description="""
Performs composite verification of a sandboxed file.

This action combines multiple validation layers:

- MIME type detection (content-based)
- Extension allowlist enforcement
- MIME allowlist enforcement
- Optional checksum validation

Returns a structured decision model including:

- Detected MIME type
- Extension validation result
- MIME allowlist compliance
- Optional checksum comparison outcome
- Final verification status

Designed for secure ingestion and validation pipelines.
""",
        tags=("file", "validation", "verification"),
        params_example=FileVerifyParams(
            path="relative/path/to/file.txt",
            expected_mime="text/plain",
            allowed_extensions=[".txt", ".md"],
            allowed_mime_types=["text/plain", "text/markdown"],
            checksum=VerifyChecksumParams(
                expected="5d41402abc4b2a76b9719d911017c592", algorithm="md5"
            ),
        ),
        result_example=FileVerifyResult(
            file_verified=True,
            size_bytes=2540,
            detected_mime="text/plain",
            extension=".txt",
            mime_matches=True,
            extension_allowed=True,
            mime_allowed=True,
            checksum_matches=True,
        ),
    )
)
