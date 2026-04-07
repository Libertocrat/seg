"""Unit tests for the SEG DSL specs loader.

These tests freeze loader-layer invariants:
- deterministic discovery of core `.yml` files only
- strict parse behavior for malformed or invalid module files
- conversion to `ModuleSpec` through structural validation only
- fail-fast semantics for bulk loading
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import seg.actions.build_engine.loader as loader_module
from seg.actions.build_engine.loader import (
    discover_spec_files,
    load_module_spec,
    load_module_specs,
)
from seg.actions.exceptions import ActionSpecsParseError
from seg.actions.schemas import ModuleSpec

# ============================================================================
# Local fixtures and helpers
# ============================================================================


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    """Return an isolated specs directory for loader tests."""
    path = tmp_path / "specs"
    path.mkdir()
    return path


@pytest.fixture
def make_module_payload():
    """Return a factory for minimal valid `ModuleSpec`-compatible payloads."""

    def _make(module_name: str) -> dict[str, Any]:
        """Build a minimal valid module payload.

        Args:
            module_name: Module namespace to embed in payload.

        Returns:
            ModuleSpec-compatible dictionary.
        """

        return {
            "version": 1,
            "module": module_name,
            "description": f"{module_name} module",
            "binaries": ["echo"],
            "actions": {
                "ping": {
                    "description": "Simple command",
                    "command": [{"binary": "echo"}],
                }
            },
        }

    return _make


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    """Write a dictionary payload to YAML file using UTF-8 encoding."""
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_yaml_str(path: Path, content: str) -> None:
    """Write raw YAML string to file using UTF-8 encoding.

    Args:
        path: Target file path.
        content: YAML string content.
    """

    path.write_text(content, encoding="utf-8")


@pytest.fixture
def valid_yaml_module_str() -> str:
    """Return a realistic SEG DSL YAML string with full feature coverage.

    This fixture represents a human-written DSL module including all supported
    elements such as args, flags, constraints, and mixed command tokens.

    Returns:
        YAML string representing a valid DSL module.
    """

    return """
version: 1
module: test_module
description: "Test module for loader"

authors:
    - "Tester <tester@example.com>"

tags: "test, loader, dsl"

binaries:
    - echo
    - printf

actions:

    complex_action:
        description: "A complex action"
        summary: "Complex test"

        args:
            input:
                type: string
                required: true
                description: "Input string"

            count:
                type: int
                required: false
                default: 5
                min: 1
                max: 10
                description: "Repeat count"

            file:
                type: file_id
                required: false
                max_size: 1024
                description: "Optional file reference"

        flags:
            verbose:
                value: "-v"
                default: false
                description: "Verbose output"

        command:
            - binary: echo
            - flag: verbose
            - "Processing:"
            - arg: input
            - "x"
            - arg: count
"""


@pytest.fixture
def make_invalid_yaml():
    """Return a factory for generating parametrically malformed YAML DSL strings.

    This fixture builds a base valid YAML structure and allows injecting
    controlled corruption via keyword flags.

    Each flag overrides a specific fragment of the YAML, enabling precise
    testing of failure scenarios while keeping the structure consistent.

    Returns:
        Callable that produces malformed YAML strings based on flags.
    """

    def _make(
        *,
        syntax_error: bool = False,
        bad_indent: bool = False,
        non_mapping_root: bool = False,
        empty: bool = False,
    ) -> str:
        """Generate malformed YAML variants for parser failure scenarios.

        Args:
            syntax_error: Produce invalid YAML syntax.
            bad_indent: Produce invalid indentation.
            non_mapping_root: Produce a non-mapping YAML root.
            empty: Produce an effectively empty YAML document.

        Returns:
            YAML string with requested malformed characteristic.
        """

        # ------------------------------------------------------------------
        # Hard overrides (highest priority)
        # ------------------------------------------------------------------

        if syntax_error:
            return "module: [broken\n"

        if non_mapping_root:
            return """
- version: 1
- module: broken
"""

        if empty:
            return "# empty YAML\n"

        # ------------------------------------------------------------------
        # Parametric fragments
        # ------------------------------------------------------------------

        command_block = """
      command:
        - binary: echo
        - arg: value
"""

        if bad_indent:
            command_block = """
      command:
        - binary: echo
         - arg: value
"""

        # ------------------------------------------------------------------
        # Final YAML assembly
        # ------------------------------------------------------------------

        return f"""
version: 1
module: broken_module
description: "Broken module"

binaries:
  - echo

actions:
  test:
    description: "Test"
{command_block}
"""

    return _make


# ============================================================================
# discover_spec_files
# ============================================================================


def test_discover_spec_files_returns_sorted_yml_files(specs_dir: Path):
    """
    GIVEN a directory with `.yml` files, other extensions, and subdirectories
    WHEN discover_spec_files is called
    THEN only `.yml` files are returned in deterministic alphabetical order
    """
    (specs_dir / "zeta.yml").write_text("version: 1\n", encoding="utf-8")
    (specs_dir / "alpha.yml").write_text("version: 1\n", encoding="utf-8")
    (specs_dir / "ignored.yaml").write_text("version: 1\n", encoding="utf-8")
    (specs_dir / "ignored.txt").write_text("hello\n", encoding="utf-8")
    (specs_dir / "nested").mkdir()

    discovered = discover_spec_files(specs_dir)

    assert [path.name for path in discovered] == ["alpha.yml", "zeta.yml"]


def test_discover_spec_files_returns_empty_list_when_no_yml_exists(specs_dir: Path):
    """
    GIVEN an existing directory with no `.yml` files
    WHEN discover_spec_files is called
    THEN an empty list is returned
    """
    (specs_dir / "file.yaml").write_text("version: 1\n", encoding="utf-8")
    (specs_dir / "notes.txt").write_text("hello\n", encoding="utf-8")

    discovered = discover_spec_files(specs_dir)

    assert discovered == []


def test_discover_spec_files_raises_when_directory_is_missing(tmp_path: Path):
    """
    GIVEN a missing specs directory path
    WHEN discover_spec_files is called
    THEN ActionSpecsParseError is raised
    """
    missing = tmp_path / "missing-specs"

    with pytest.raises(
        ActionSpecsParseError,
        match="Failed to discover DSL spec files",
    ):
        discover_spec_files(missing)


def test_discover_spec_files_raises_when_path_is_not_directory(tmp_path: Path):
    """
    GIVEN a path that exists as a regular file
    WHEN discover_spec_files is called
    THEN ActionSpecsParseError is raised
    """
    file_path = tmp_path / "not_a_directory"
    file_path.write_text("not-a-dir\n", encoding="utf-8")

    with pytest.raises(
        ActionSpecsParseError,
        match="Failed to discover DSL spec files",
    ):
        discover_spec_files(file_path)


# ============================================================================
# load_module_spec
# ============================================================================


def test_load_module_spec_returns_modulespec_for_valid_yml(
    specs_dir: Path,
    make_module_payload,
):
    """
    GIVEN a structurally valid DSL `.yml` module
    WHEN load_module_spec is called
    THEN a validated ModuleSpec instance is returned
    """
    spec_file = specs_dir / "valid.yml"
    write_yaml(spec_file, make_module_payload("checksum"))

    module = load_module_spec(spec_file)

    assert isinstance(module, ModuleSpec)
    assert module.module == "checksum"


def test_load_module_spec_raises_for_invalid_yaml(specs_dir: Path):
    """
    GIVEN a `.yml` file with invalid YAML syntax
    WHEN load_module_spec is called
    THEN ActionSpecsParseError is raised with a masked path message
    """
    spec_file = specs_dir / "invalid_yaml.yml"
    spec_file.write_text("module: [broken\n", encoding="utf-8")

    with pytest.raises(ActionSpecsParseError, match="CORE/invalid_yaml.yml"):
        load_module_spec(spec_file)


def test_load_module_spec_raises_for_empty_yaml(specs_dir: Path):
    """
    GIVEN an empty YAML document
    WHEN load_module_spec is called
    THEN ActionSpecsParseError is raised
    """
    spec_file = specs_dir / "empty.yml"
    spec_file.write_text("# comments only\n", encoding="utf-8")

    with pytest.raises(ActionSpecsParseError, match="YAML document is empty"):
        load_module_spec(spec_file)


@pytest.mark.parametrize(
    "yaml_content",
    [
        "- item1\n- item2\n",
        "plain-string\n",
        "123\n",
    ],
    ids=[
        "yaml_root_list",
        "yaml_root_scalar_string",
        "yaml_root_scalar_int",
    ],
)
def test_load_module_spec_raises_when_yaml_root_is_not_mapping(
    specs_dir: Path,
    yaml_content: str,
):
    """
    GIVEN a YAML document whose root is not a mapping
    WHEN load_module_spec is called
    THEN ActionSpecsParseError is raised
    """
    spec_file = specs_dir / "bad_root.yml"
    spec_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(ActionSpecsParseError, match="YAML root must be a mapping"):
        load_module_spec(spec_file)


def test_load_module_spec_raises_when_modulespec_validation_fails(
    specs_dir: Path,
):
    """
    GIVEN a YAML mapping that fails ModuleSpec structural validation
    WHEN load_module_spec is called
    THEN ActionSpecsParseError is raised
    """
    spec_file = specs_dir / "invalid_schema.yml"
    write_yaml(
        spec_file,
        {
            "version": 1,
            "module": "broken",
        },
    )

    with pytest.raises(
        ActionSpecsParseError,
        match="Failed to validate DSL module 'CORE/invalid_schema.yml'",
    ):
        load_module_spec(spec_file)


# ============================================================================
# load_module_spec (specs YAML realism layer)
# ============================================================================


def test_load_module_spec_parses_realistic_yaml(
    specs_dir: Path,
    valid_yaml_module_str: str,
):
    """
    GIVEN a realistic specs YAML module with args, flags, and mixed command tokens
    WHEN load_module_spec is called
    THEN a valid ModuleSpec is returned preserving structure
    """
    spec_file = specs_dir / "realistic.yml"
    write_yaml_str(spec_file, valid_yaml_module_str)

    module = load_module_spec(spec_file)

    assert module.module == "test_module"
    assert "complex_action" in module.actions

    action = module.actions["complex_action"]

    assert action.args is not None
    assert action.flags is not None

    assert "input" in action.args
    assert "count" in action.args
    assert "verbose" in action.flags

    assert len(action.command) > 0


@pytest.mark.parametrize(
    "error_case",
    [
        "syntax_error",
        "bad_indent",
        "non_mapping_root",
        "empty",
    ],
    ids=[
        "invalid_yaml_syntax",
        "bad_indentation",
        "non_mapping_root",
        "empty_yaml",
    ],
)
def test_load_module_spec_fails_on_invalid_yaml_variants(
    specs_dir: Path,
    make_invalid_yaml,
    error_case: str,
):
    """
    GIVEN malformed YAML variants generated by `make_invalid_yaml`
    WHEN load_module_spec is called
    THEN ActionSpecsParseError is raised for each variant
    """

    # Explicit mapping (prevents silent mismatch bugs)
    kwargs_map = {
        "syntax_error": {"syntax_error": True},
        "bad_indent": {"bad_indent": True},
        "non_mapping_root": {"non_mapping_root": True},
        "empty": {"empty": True},
    }

    spec_file = specs_dir / f"{error_case}.yml"
    write_yaml_str(spec_file, make_invalid_yaml(**kwargs_map[error_case]))

    with pytest.raises(ActionSpecsParseError):
        load_module_spec(spec_file)


# ============================================================================
# load_module_specs
# ============================================================================


def test_load_module_specs_returns_all_valid_modules(
    specs_dir: Path,
    make_module_payload,
):
    """
    GIVEN multiple valid `.yml` files in one directory
    WHEN load_module_specs is called
    THEN all ModuleSpec objects are returned in deterministic file order
    """
    write_yaml(specs_dir / "a_first.yml", make_module_payload("first_mod"))
    write_yaml(specs_dir / "b_second.yml", make_module_payload("second_mod"))

    modules = load_module_specs(specs_dir)

    assert [module.module for module in modules] == ["first_mod", "second_mod"]
    assert all(isinstance(module, ModuleSpec) for module in modules)


def test_load_module_specs_returns_empty_list_when_directory_has_no_yml(
    specs_dir: Path,
):
    """
    GIVEN an existing directory with no `.yml` files
    WHEN load_module_specs is called
    THEN an empty list is returned
    """
    (specs_dir / "ignored.yaml").write_text("version: 1\n", encoding="utf-8")

    modules = load_module_specs(specs_dir)

    assert modules == []


def test_load_module_specs_fails_fast_on_first_invalid_file(
    specs_dir: Path,
    make_module_payload,
    monkeypatch,
):
    """
    GIVEN multiple `.yml` files where the first discovered one is invalid
    WHEN load_module_specs is called
    THEN ActionSpecsParseError is raised and loading stops immediately
    """
    invalid_file = specs_dir / "a_invalid.yml"
    invalid_file.write_text("module: [broken\n", encoding="utf-8")
    write_yaml(specs_dir / "b_valid.yml", make_module_payload("valid_mod"))

    real_load_module_spec = loader_module.load_module_spec
    calls: list[str] = []

    def _tracking_load(path: Path) -> ModuleSpec:
        """Record load order and delegate to the real loader."""
        calls.append(path.name)
        return real_load_module_spec(path)

    monkeypatch.setattr(loader_module, "load_module_spec", _tracking_load)

    with pytest.raises(ActionSpecsParseError, match="CORE/a_invalid.yml"):
        load_module_specs(specs_dir)

    assert calls == ["a_invalid.yml"]
