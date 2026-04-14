"""Startup loader for SEG DSL module specifications.

This module performs deterministic discovery and strict structural parsing of
DSL YAML module specification files into `ModuleSpec` objects.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from seg.actions.engine_config import (
    ALLOWED_CONTROL_CHARS,
    ALLOWED_SPEC_EXTENSIONS,
    CORE_MASK_PREFIX,
    CORE_SPECS_DIR,
    DISALLOWED_YAML_PATTERNS,
    USER_MASK_PREFIX,
    USER_SPECS_DIR,
)
from seg.actions.exceptions import ActionSpecsParseError
from seg.actions.schemas.module import ModuleSpec
from seg.core.config import Settings

logger = logging.getLogger("seg.actions.build_engine.loader")


def discover_spec_files(spec_dirs: list[Path]) -> list[Path]:
    """Discover SEG DSL spec files from ordered directories.

    Args:
        spec_dirs: Ordered list of directories to scan.

    Returns:
        Deterministically ordered list of discovered spec files.

    Raises:
        ActionSpecsParseError: If an existing path is not a directory, if
            a subdirectory is present, if an invalid extension is present,
            or if discovery fails.
    """

    discovered: list[Path] = []

    for spec_dir in spec_dirs:
        if not spec_dir.exists():
            logger.info(
                "Skipping missing SEG DSL specs directory: %s",
                _mask_path(spec_dir),
            )
            continue

        if not spec_dir.is_dir():
            masked_dir = _mask_path(spec_dir)
            logger.error(
                "Invalid SEG DSL specs path: '%s' is not a directory",
                masked_dir,
            )
            raise ActionSpecsParseError(
                f"Invalid SEG DSL specs path: '{masked_dir}' is not a directory"
            )

        discovered.extend(_discover_spec_files_in_dir(spec_dir))

    logger.info("Discovered %d SEG DSL spec file(s)", len(discovered))
    return discovered


def _discover_spec_files_in_dir(spec_dir: Path) -> list[Path]:
    """Discover and validate files in one specs directory.

    Args:
        spec_dir: Existing directory to scan.

    Returns:
        Sorted list of valid YAML spec files.

    Raises:
        ActionSpecsParseError: If listing fails, if nested directories are
            present, or if files with invalid extension are present.
    """

    masked_dir = _mask_path(spec_dir)
    logger.info("Scanning SEG DSL specs directory: %s", masked_dir)

    try:
        entries = sorted(spec_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        logger.error("Failed to discover SEG DSL spec files in '%s'", masked_dir)
        raise ActionSpecsParseError(
            f"Failed to discover SEG DSL spec files in '{masked_dir}'"
        ) from exc

    valid_files: list[Path] = []
    for path in entries:
        masked_path = _mask_path(path)

        if path.is_dir():
            logger.error("Nested directories are not allowed in '%s'", masked_dir)
            raise ActionSpecsParseError(
                f"Nested directories are not allowed in '{masked_dir}': '{masked_path}'"
            )

        if not path.is_file():
            continue

        if path.suffix not in ALLOWED_SPEC_EXTENSIONS:
            logger.error("Invalid SEG DSL spec extension in '%s'", masked_path)
            raise ActionSpecsParseError(
                (
                    f"Invalid SEG DSL spec extension in '{masked_path}': "
                    f"allowed={ALLOWED_SPEC_EXTENSIONS}"
                )
            )

        valid_files.append(path)

    return valid_files


def validate_yaml_file_safety(path: Path, settings: Settings) -> None:
    """Validate YAML file safety constraints before parsing.

    Args:
        path: Path to YAML file.
        settings: Runtime settings with size limits.

    Raises:
        ActionSpecsParseError: If file size/content violates safety rules.
    """

    masked_path = _mask_path(path)

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        logger.error("Failed to stat DSL module '%s'", masked_path)
        raise ActionSpecsParseError(
            f"Failed to stat DSL module '{masked_path}'"
        ) from exc

    max_yml_size_bytes = getattr(settings, "seg_max_yml_size_bytes", 100 * 1024)

    if file_size > max_yml_size_bytes:
        logger.error("DSL module '%s' exceeds max allowed size", masked_path)
        raise ActionSpecsParseError(
            (
                f"DSL module '{masked_path}' exceeds maximum allowed size "
                f"({max_yml_size_bytes} bytes)"
            )
        )

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        logger.error("Failed to read DSL module '%s' as UTF-8", masked_path)
        raise ActionSpecsParseError(
            f"Failed to read DSL module '{masked_path}' as UTF-8"
        ) from exc

    if "\x00" in content:
        logger.error("DSL module '%s' contains NUL byte", masked_path)
        raise ActionSpecsParseError(f"DSL module '{masked_path}' contains NUL byte")

    if any(ord(char) < 32 and char not in ALLOWED_CONTROL_CHARS for char in content):
        logger.error(
            "DSL module '%s' contains disallowed control characters",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"DSL module '{masked_path}' contains disallowed control characters"
        )

    for pattern in DISALLOWED_YAML_PATTERNS:
        if pattern in content:
            logger.error(
                "DSL module '%s' contains disallowed YAML pattern",
                masked_path,
            )
            raise ActionSpecsParseError(
                (
                    f"DSL module '{masked_path}' contains disallowed YAML pattern: "
                    f"'{pattern}'"
                )
            )


def load_module_spec(path: Path) -> ModuleSpec:
    """Load one SEG DSL module file as a validated `ModuleSpec`.


    Args:
        path: Path to a YAML module definition file.

    Returns:
        Parsed and structurally validated `ModuleSpec`.

    Raises:
        ActionSpecsParseError: If file reading/parsing fails or
            `ModuleSpec` validation fails.
    """

    data = _read_yaml_mapping(path)
    return _generate_module_spec_model(data, path)


def load_module_specs(
    spec_dirs: list[Path],
    settings: Settings,
) -> list[ModuleSpec]:
    """Load all discovered SEG DSL spec files from ordered directories.

    Args:
        spec_dirs: Ordered directories expected to contain SEG DSL YAML files.
        settings: Runtime settings used for safety checks.

    Returns:
        List of parsed `ModuleSpec` objects in deterministic order.

    Raises:
        ActionSpecsParseError: If discovery fails or any module file fails
            strict loading/validation.
    """

    logger.info("Starting SEG DSL module bulk load")

    spec_files = discover_spec_files(spec_dirs)
    if not spec_files:
        return []

    modules: list[ModuleSpec] = []
    seen_module_names: set[str] = set()

    for path in spec_files:
        validate_yaml_file_safety(path, settings)
        module = load_module_spec(path)

        if module.module != path.stem:
            masked_path = _mask_path(path)
            logger.error(
                "Module name mismatch in '%s': module='%s' filename='%s'",
                masked_path,
                module.module,
                path.stem,
            )
            raise ActionSpecsParseError(
                (
                    f"Module name mismatch in '{masked_path}': "
                    f"module='{module.module}' filename='{path.stem}'"
                )
            )

        if module.module in seen_module_names:
            masked_path = _mask_path(path)
            logger.error(
                "Duplicate module '%s' discovered in '%s'",
                module.module,
                masked_path,
            )
            raise ActionSpecsParseError(
                f"Duplicate module name '{module.module}' discovered in '{masked_path}'"
            )

        seen_module_names.add(module.module)
        modules.append(module)

    logger.info("Successfully loaded %d SEG DSL module(s)", len(modules))
    return modules


def _mask_path(path: Path) -> str:
    """Return safe masked path representation for logs and errors.

    Args:
        path: Source filesystem path.

    Returns:
        Masked path according to configured core/user directories.
    """

    if path.parent == CORE_SPECS_DIR:
        return f"{CORE_MASK_PREFIX}/{path.name}"
    if path.parent == USER_SPECS_DIR:
        return f"{USER_MASK_PREFIX}/{path.name}"
    return str(path)


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read YAML file and enforce a non-empty top-level mapping.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed YAML mapping suitable for `ModuleSpec.model_validate`.

    Raises:
        ActionSpecsParseError: If file read fails, YAML syntax is invalid,
            document is empty, or root is not a mapping.
    """

    masked_path = _mask_path(path)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        logger.error(
            "Failed to parse DSL module '%s': unable to read file",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to parse DSL module '{masked_path}': unable to read file"
        ) from exc

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        logger.error(
            "Failed to parse DSL module '%s': invalid YAML syntax",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to parse DSL module '{masked_path}': invalid YAML syntax"
        ) from exc

    if parsed is None:
        logger.error(
            "Failed to parse DSL module '%s': YAML document is empty",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to parse DSL module '{masked_path}': YAML document is empty"
        )

    if not isinstance(parsed, dict):
        logger.error(
            "Failed to parse DSL module '%s': YAML root must be a mapping",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to parse DSL module '{masked_path}': YAML root must be a mapping"
        )

    return parsed


def _generate_module_spec_model(data: dict[str, Any], path: Path) -> ModuleSpec:
    """Validate parsed mapping as `ModuleSpec`.

    Args:
        data: Parsed YAML mapping for one module file.
        path: Source file path used for masked logging and errors.

    Returns:
        Validated `ModuleSpec` object.

    Raises:
        ActionSpecsParseError: If module validation fails or an unexpected
            validation-side exception occurs.
    """

    masked_path = _mask_path(path)

    try:
        module_spec = ModuleSpec.model_validate(data)
    except ValidationError as exc:
        logger.error(
            "Failed to validate DSL module '%s' against ModuleSpec",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to validate DSL module '{masked_path}' against ModuleSpec"
        ) from exc
    except Exception as exc:
        logger.error(
            "Failed to parse DSL module '%s': unexpected loader error",
            masked_path,
        )
        raise ActionSpecsParseError(
            f"Failed to parse DSL module '{masked_path}': unexpected loader error"
        ) from exc

    logger.info(
        "Loaded DSL module from %s (module=%s)",
        masked_path,
        module_spec.module,
    )
    return module_spec
