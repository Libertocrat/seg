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


# ============================================================================
# Action Registration
# ============================================================================


def test_register_action_successfully(clean_action_registry):
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


def test_registering_duplicate_action_raises_error(clean_action_registry):
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
# Action Lookup
# ============================================================================


def test_get_action_returns_none_for_unknown_action():
    """
    GIVEN an empty registry
    WHEN an unknown action name is requested
    THEN None is returned
    """
    result = get_action("non_existent_action")

    assert result is None


def test_get_action_returns_correct_action(clean_action_registry):
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


def test_list_actions_returns_sorted_action_names(clean_action_registry):
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


def test_list_actions_is_empty_when_no_actions_registered(clean_action_registry):
    """
    GIVEN an empty registry
    WHEN list_actions is called
    THEN an empty list is returned
    """
    result = list_actions()

    assert result == []


# ============================================================================
# Registry snapshot and restore
# ============================================================================


def test_registry_public_helpers_snapshot_and_restore(clean_action_registry):
    """
    GIVEN a registry with an initial snapshot
    WHEN a temporary action is registered and `restore_registry` is called
    THEN the temporary action is removed and the original snapshot is restored
    """
    from seg.actions import registry

    # Capture current state
    snapshot = registry.get_registry_snapshot()

    # Register a temporary action
    spec = ActionSpec(
        name="tmp_helper_action",
        params_model=DummyActionParams,
        handler=dummy_action_handler,
    )
    register_action(spec)

    # Ensure the action is registered now
    assert "tmp_helper_action" in list_actions()

    # Restore snapshot and ensure the temporary action is gone
    registry.restore_registry(snapshot)
    assert "tmp_helper_action" not in list_actions()


def test_registry_replace_and_clear_registry(clean_action_registry):
    """
    GIVEN the current registry state
    WHEN `replace_registry({})` is used and `clear_registry()` and new
        registrations are performed on the replacement
    THEN the replacement registry reflects those changes and the original
        registry can be restored without pollution
    """
    from seg.actions import registry

    # Shallow copy of the current registry for later restoration
    original = registry.get_registry_snapshot()

    try:
        # Replace with an explicitly controlled registry
        registry.replace_registry({})
        assert list_actions() == []

        # Clear on empty should be a no-op and not raise
        registry.clear_registry()
        assert list_actions() == []

        # Populate the replacement registry and ensure it's visible
        spec = ActionSpec(
            name="replace_action",
            params_model=DummyActionParams,
            handler=dummy_action_handler,
        )
        register_action(spec)
        assert "replace_action" in list_actions()

    finally:
        # Restore original and ensure it's back to the initial state
        registry.restore_registry(original)
        assert registry.get_registry_snapshot() == original


def test_get_registry_snapshot_is_shallow_copy(clean_action_registry):
    """
    GIVEN a registry snapshot retrieved via `get_registry_snapshot`
    WHEN the returned snapshot object is mutated
    THEN the live registry remains unchanged
    """
    from seg.actions import registry

    copy_snapshot = registry.get_registry_snapshot()

    # Mutate the returned copy and ensure live registry unchanged
    copy_snapshot["__fake__"] = "some value"
    assert "__fake__" not in registry.get_registry_snapshot()
