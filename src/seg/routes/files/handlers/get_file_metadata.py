"""GET /v1/files/{file_id} metadata route handler."""

from __future__ import annotations

import uuid

from seg.core.config import Settings, get_settings
from seg.core.utils.file_storage import logger
from seg.routes.files.schemas import FileMetadata
from seg.routes.files.utils import safe_load_metadata


async def get_file_metadata_handler(
    file_id: uuid.UUID,
    settings: Settings | None = None,
) -> FileMetadata:
    """Load metadata for a previously uploaded file.

    This handler orchestrates storage access and maps low-level errors into
    SEG's standardized error model.

    Error mapping:
    - FILE_NOT_FOUND → metadata file does not exist
    - INVALID_REQUEST → metadata exists but is invalid/corrupted
    - INTERNAL_ERROR → unexpected system or IO failure
    """

    cfg = settings or get_settings()
    metadata = safe_load_metadata(file_id, cfg)

    logger.info(
        "file.metadata.retrieved",
        extra={"file_id": str(file_id)},
    )

    return metadata
