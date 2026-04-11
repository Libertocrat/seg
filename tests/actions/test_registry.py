"""
Unit tests for the SEG DSL runtime registry.

These tests freeze immutable registry invariants:
- loading and compiling DSL modules
- deterministic action lookup
- explicit not-found behavior
- stable listing and membership semantics
"""

from __future__ import annotations

import pytest

from seg.actions.exceptions import ActionNotFoundError
from seg.actions.models import ActionSpec
from seg.actions.registry import ActionRegistry, build_registry_from_specs
from seg.core.config import Settings

# ============================================================================
# Registry Build
# ============================================================================


def test_build_registry_from_specs_success(tmp_path):
    """
    GIVEN a minimal valid DSL module under a temporary specs directory
    WHEN build_registry_from_specs is called
    THEN it returns an ActionRegistry with the declared action available
    """
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    (specs_dir / "sample.yml").write_text(
        """
version: 1
module: sample
description: "Sample runtime module"
binaries:
  - echo

actions:
  ping:
    description: "Ping action"
    summary: "Ping"
    command:
      - binary: echo
      - "hello"
""".strip(),
        encoding="utf-8",
    )

    settings = Settings.model_validate(
        {
            "seg_root_dir": str(tmp_path),
        }
    )

    registry = build_registry_from_specs(specs_dir, settings)

    assert isinstance(registry, ActionRegistry)
    assert registry.has("sample.ping") is True

    spec = registry.get("sample.ping")
    assert isinstance(spec, ActionSpec)


# ============================================================================
# Action Lookup
# ============================================================================


def test_registry_get_returns_action_spec(valid_registry):
    """
    GIVEN a valid immutable registry
    WHEN one known action is retrieved via get()
    THEN the returned object is an ActionSpec
    """
    result = valid_registry.get("test_runtime.ping")

    assert isinstance(result, ActionSpec)
    assert result.name == "test_runtime.ping"


def test_registry_get_unknown_action_raises(valid_registry):
    """
    GIVEN a valid immutable registry
    WHEN an unknown action is requested via get()
    THEN ActionNotFoundError is raised
    """
    with pytest.raises(ActionNotFoundError):
        valid_registry.get("test_runtime.missing")


# ============================================================================
# Membership and listing
# ============================================================================


def test_registry_has(valid_registry):
    """
    GIVEN a valid immutable registry
    WHEN has() is called with known and unknown actions
    THEN it returns True for existing names and False otherwise
    """
    assert valid_registry.has("test_runtime.ping") is True
    assert valid_registry.has("test_runtime.unknown") is False


def test_registry_list_names_sorted(valid_registry):
    """
    GIVEN a valid immutable registry with multiple actions
    WHEN list_names() is called
    THEN names are returned in deterministic sorted order
    """
    names = valid_registry.list_names()

    assert isinstance(names, tuple)
    assert names == tuple(sorted(names))
    assert "test_runtime.ping" in names
    assert "test_runtime.repeat" in names
