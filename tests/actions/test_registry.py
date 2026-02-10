"""
Unit tests for the SEG action registry.

These tests freeze the invariants of the action registration mechanism:
- explicit registration
- duplicate prevention
- deterministic lookup
- registry isolation between tests
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from seg.actions.registry import (
    ActionSpec,
    get_action,
    list_actions,
    register_action,
)

# ============================================================================
# Test helpers
# ============================================================================


class DummyActionParams(BaseModel):
    """Minimal params model for registry testing."""

    value: int


async def dummy_action_handler(params: DummyActionParams):
    """Minimal async handler used for registry tests."""
    return {"value": params.value}


@pytest.fixture(autouse=True)
def clear_action_registry():
    """
    GIVEN a global in-memory action registry
    WHEN a test starts
    THEN the registry is cleared to guarantee isolation
    """
    # Import locally to avoid exposing the private symbol globally
    from seg.actions import registry

    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


# ============================================================================
# Action registration
# ============================================================================


def test_register_action_successfully():
    """
    GIVEN a valid ActionSpec
    WHEN the action is registered
    THEN it can be retrieved by name from the registry
    """
    spec = ActionSpec(
        name="dummy_action",
        params_model=DummyActionParams,
        handler=dummy_action_handler,
    )

    register_action(spec)

    retrieved = get_action("dummy_action")

    assert retrieved is spec
    assert retrieved.name == "dummy_action"
    assert retrieved.params_model is DummyActionParams
    assert retrieved.handler is dummy_action_handler


def test_registering_duplicate_action_raises_error():
    """
    GIVEN an action already registered under a name
    WHEN another action with the same name is registered
    THEN a RuntimeError is raised
    """
    spec = ActionSpec(
        name="duplicate_action",
        params_model=DummyActionParams,
        handler=dummy_action_handler,
    )

    register_action(spec)

    with pytest.raises(RuntimeError, match="Action already registered"):
        register_action(spec)


# ============================================================================
# Action lookup
# ============================================================================


def test_get_action_returns_none_for_unknown_action():
    """
    GIVEN an empty registry
    WHEN an unknown action name is requested
    THEN None is returned
    """
    result = get_action("non_existent_action")

    assert result is None


def test_get_action_returns_correct_action():
    """
    GIVEN a registered action
    WHEN it is retrieved by name
    THEN the correct ActionSpec is returned
    """
    spec = ActionSpec(
        name="lookup_action",
        params_model=DummyActionParams,
        handler=dummy_action_handler,
    )

    register_action(spec)

    result = get_action("lookup_action")

    assert result is spec


# ============================================================================
# Registry listing
# ============================================================================


def test_list_actions_returns_sorted_action_names():
    """
    GIVEN multiple registered actions
    WHEN list_actions is called
    THEN action names are returned in sorted order
    """
    names = ["z_action", "a_action", "m_action"]

    for name in names:
        register_action(
            ActionSpec(
                name=name,
                params_model=DummyActionParams,
                handler=dummy_action_handler,
            )
        )

    result = list_actions()

    assert result == sorted(names)


def test_list_actions_is_empty_when_no_actions_registered():
    """
    GIVEN an empty registry
    WHEN list_actions is called
    THEN an empty list is returned
    """
    result = list_actions()

    assert result == []
