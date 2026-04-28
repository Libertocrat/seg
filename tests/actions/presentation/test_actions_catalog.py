"""Unit tests for SEG action presentation catalog helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

import pytest

from seg.actions.models.core import ActionSpec
from seg.actions.models.presentation import ModuleSummary
from seg.actions.presentation.catalog import (
    build_module_summaries,
    filter_modules,
    get_action,
)

# ============================================================================
# Fixtures
# ============================================================================


def _deep_normalize(value: object) -> object:
    """Recursively normalize values to comparable plain structures."""

    if is_dataclass(value) and not isinstance(value, type):
        return _deep_normalize(asdict(value))

    if isinstance(value, dict):
        return {key: _deep_normalize(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_deep_normalize(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_deep_normalize(item) for item in value)

    return value


@pytest.fixture
def registry_modules_and_actions(
    valid_registry,
) -> tuple[list[object], dict[str, ActionSpec]]:
    """Extract real modules and actions from a built registry."""

    modules = valid_registry.modules
    actions = {name: valid_registry.get(name) for name in valid_registry.list_names()}

    return modules, actions


# ============================================================================
# BUILD MODULE SUMMARIES
# ============================================================================


def test_build_module_summaries_from_valid_registry(
    registry_modules_and_actions,
) -> None:
    """
    GIVEN a fully built registry
    WHEN building summaries
    THEN real modules and actions must be grouped correctly
    """

    modules, actions = registry_modules_and_actions

    result = build_module_summaries(modules, actions)

    assert len(result) > 0

    module = result[0]

    assert isinstance(module, ModuleSummary)
    assert isinstance(module.module_id, str)
    assert isinstance(module.actions, list)
    assert all(action.action_name for action in module.actions)


def test_module_summaries_include_real_action_names(
    registry_modules_and_actions,
) -> None:
    """
    GIVEN a real registry
    WHEN building summaries
    THEN action names must match registry keys
    """

    modules, actions = registry_modules_and_actions

    result = build_module_summaries(modules, actions)

    action_names = {
        action.action_name for module in result for action in module.actions
    }
    registry_names = set(actions.keys())

    assert action_names.issubset(registry_names)


def test_module_namespace_consistency(registry_modules_and_actions) -> None:
    """
    GIVEN real modules
    WHEN building summaries
    THEN namespace and namespace_path must be consistent
    """

    modules, actions = registry_modules_and_actions

    result = build_module_summaries(modules, actions)

    for module in result:
        assert module.namespace == ".".join(module.namespace_path)


def test_build_module_summaries_sorted(registry_modules_and_actions) -> None:
    """
    GIVEN real module summaries
    WHEN building summaries
    THEN results must be deterministically sorted by module_id
    """

    modules, actions = registry_modules_and_actions

    result = build_module_summaries(modules, actions)

    assert result == sorted(result, key=lambda module: module.module_id)


# ============================================================================
# FILTER MODULES
# ============================================================================


def test_filter_modules_query_real_data(registry_modules_and_actions) -> None:
    """
    GIVEN real module summaries
    WHEN filtering by query
    THEN results must match actual descriptions or names
    """

    modules, actions = registry_modules_and_actions
    summaries = build_module_summaries(modules, actions)

    result = filter_modules(summaries, q="test")

    assert isinstance(result, list)
    query = "test"

    for module in result:
        module_match = (
            query in module.module_id.lower() or query in module.description.lower()
        )
        action_match = any(
            query in action.action_name.lower()
            or query in (action.summary or "").lower()
            or query in (action.description or "").lower()
            for action in module.actions
        )
        assert module_match or action_match


def test_filter_modules_tag_real(registry_modules_and_actions) -> None:
    """
    GIVEN real modules with tags
    WHEN filtering by tag
    THEN tag matching must be case-insensitive and normalized
    """

    modules, actions = registry_modules_and_actions
    summaries = build_module_summaries(modules, actions)

    result_upper = filter_modules(summaries, tag="TEST")
    result_lower = filter_modules(summaries, tag="test")

    expected = [
        module for module in summaries if "test" in {tag.lower() for tag in module.tags}
    ]

    assert isinstance(result_upper, list)
    assert _deep_normalize(result_upper) == _deep_normalize(result_lower)
    assert _deep_normalize(result_upper) == _deep_normalize(expected)
    assert all(
        "test" in {tag.lower() for tag in module.tags} for module in result_upper
    )


# ============================================================================
# GET ACTION
# ============================================================================


def test_get_action_from_mapping(registry_modules_and_actions) -> None:
    """
    GIVEN action mapping
    WHEN retrieving action
    THEN correct spec must be returned
    """

    _modules, actions = registry_modules_and_actions
    action_name = next(iter(actions.keys()))

    result = get_action(actions, action_name)

    assert result is actions[action_name]
    assert _deep_normalize(result.model_dump()) == _deep_normalize(
        actions[action_name].model_dump()
    )


def test_registry_cache_matches_catalog(valid_registry) -> None:
    """
    GIVEN a built registry
    WHEN comparing cache with catalog builder
    THEN both must be identical
    """

    modules = valid_registry.modules
    actions = {name: valid_registry.get(name) for name in valid_registry.list_names()}

    rebuilt = build_module_summaries(modules, actions)

    assert _deep_normalize(valid_registry.module_summaries) == _deep_normalize(rebuilt)
