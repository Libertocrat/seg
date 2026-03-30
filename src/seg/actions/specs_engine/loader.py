"""Startup loader for SEG DSL v1 core module specifications.

This module performs only deterministic discovery and structural parsing of
core `.yml` spec files into `ModuleSpec` objects.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from seg.actions.schemas import ModuleSpec
from seg.actions.specs_engine.exceptions import ActionSpecsParseError

logger = logging.getLogger("seg.actions.specs_engine.loader")


def discover_spec_files(specs_dir: Path) -> list[Path]:
    """Discover SEG DSL core spec files from `specs_dir`.

    Args:
        specs_dir: Directory expected to contain core SEG DSL `.yml` files.

    Returns:
        Sorted list of `.yml` files found directly under `specs_dir`.

    Raises:
        ActionSpecsParseError: If the provided path is missing, is not a
            directory, or directory listing fails.
    """

    logger.info("Loading SEG DSL core specs from actions/specs")

    if not specs_dir.exists():
        logger.error("Failed to discover DSL spec files in CORE directory")
        raise ActionSpecsParseError(
            "Failed to discover DSL spec files in CORE directory"
        )

    if not specs_dir.is_dir():
        logger.error("Failed to discover DSL spec files in CORE directory")
        raise ActionSpecsParseError(
            "Failed to discover DSL spec files in CORE directory"
        )

    try:
        spec_files = sorted(
            [
                path
                for path in specs_dir.iterdir()
                if path.is_file() and path.suffix == ".yml"
            ],
            key=lambda path: path.name,
        )
    except OSError as exc:
        logger.error(
            "Failed to discover DSL spec files in CORE directory: %s",
            exc,
        )
        raise ActionSpecsParseError(
            "Failed to discover DSL spec files in CORE directory"
        ) from exc

    logger.info("Discovered %d SEG DSL core spec file(s)", len(spec_files))
    if not spec_files:
        logger.info("No SEG DSL core spec files found in actions/specs")

    return spec_files


def load_module_spec(path: Path) -> ModuleSpec:
    """Load one SEG DSL module file as a validated `ModuleSpec`.

    Args:
        path: Path to a `.yml` module definition file.

    Returns:
        Parsed and structurally validated `ModuleSpec`.

    Raises:
        ActionSpecsParseError: If file reading/parsing fails or
            `ModuleSpec` validation fails.
    """

    data = _read_yaml_mapping(path)
    return _generate_module_spec_model(data, path)


def load_module_specs(specs_dir: Path) -> list[ModuleSpec]:
    """Load all discovered SEG DSL core spec files from `specs_dir`.

    Args:
        specs_dir: Directory expected to contain SEG DSL `.yml` files.

    Returns:
        List of parsed `ModuleSpec` objects in deterministic order.

    Raises:
        ActionSpecsParseError: If discovery fails or any module file fails
            strict loading/validation.
    """

    logger.info("Starting SEG DSL core module bulk load")

    spec_files = discover_spec_files(specs_dir)
    if not spec_files:
        return []

    modules = [load_module_spec(path) for path in spec_files]
    logger.info("Successfully loaded %d SEG DSL module(s)", len(modules))
    return modules


def _masked_core_path(path: Path) -> str:
    """Return safe masked path representation for logs and errors.

    Args:
        path: Source filesystem path.

    Returns:
        Masked file path in the `CORE/<filename>` format.
    """

    return f"CORE/{path.name}"


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

    masked_path = _masked_core_path(path)

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

    masked_path = _masked_core_path(path)

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
