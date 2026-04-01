"""Reusable fixtures and factories for SEG DSL action engine tests.

This module centralizes small, composable factories used by tests for the
YAML-based action definition engine so loader, validator, and future specs
engine tests can share the same baseline payload builders.
"""

from __future__ import annotations

from typing import Any

import pytest

from seg.actions.schemas import ModuleSpec

# ============================================================================
# Action payload factories
# ============================================================================


@pytest.fixture
def make_action_spec_input():
    """Return a factory for ActionSpecInput-compatible dictionaries.

    Returns:
        A callable that builds raw action payloads without YAML parsing.
    """

    def _make(
        *,
        description: str = "test action",
        summary: str | None = None,
        args: dict[str, Any] | None = None,
        flags: dict[str, Any] | None = None,
        command: list[Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "description": description,
            "summary": summary,
            "args": args,
            "flags": flags,
            "command": [{"binary": "echo"}] if command is None else command,
        }

    return _make


@pytest.fixture
def make_action_payload(make_action_spec_input):
    """Return a factory for minimal valid action payloads.

    This fixture remains as a compatibility alias for existing test files.

    Returns:
        A callable that builds `ActionSpecInput`-compatible dictionaries.
    """

    def _make(
        *,
        args: dict[str, Any] | None = None,
        flags: dict[str, Any] | None = None,
        command: list[Any] | None = None,
    ) -> dict[str, Any]:
        return make_action_spec_input(
            description="test",
            args=args,
            flags=flags,
            command=command,
        )

    return _make


# ============================================================================
# Module payload factories
# ============================================================================


@pytest.fixture
def make_module_payload(make_action_payload):
    """Return a factory for minimal valid `ModuleSpec` payloads.

    Args:
            make_action_payload: Fixture returning the reusable action payload
                    factory.

    Returns:
            A callable that builds `ModuleSpec`-compatible dictionaries with
            optional field overrides.
    """

    def _make(
        module_name: str = "test_module",
        *,
        version: int = 1,
        binaries: list[str] | None = None,
        actions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "version": version,
            "module": module_name,
            "description": f"{module_name} module",
            "binaries": ["echo"] if binaries is None else binaries,
            "actions": {"ping": make_action_payload()} if actions is None else actions,
        }

    return _make


@pytest.fixture
def make_module_spec():
    """Return a factory that converts payload dictionaries into `ModuleSpec`.

    Returns:
            A callable that validates a payload with `ModuleSpec.model_validate`.
    """

    def _make(payload: dict[str, Any]) -> ModuleSpec:
        return ModuleSpec.model_validate(payload)

    return _make


@pytest.fixture
def make_valid_module(make_module_payload, make_module_spec):
    """Return a factory for a minimal semantically valid `ModuleSpec`.

    Args:
            make_module_payload: Fixture returning the reusable module payload
                    factory.
            make_module_spec: Fixture converting payloads into `ModuleSpec`
                    instances.

    Returns:
            A callable that returns a valid `ModuleSpec` instance.
    """

    def _make() -> ModuleSpec:
        return make_module_spec(make_module_payload())

    return _make
