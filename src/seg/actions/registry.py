"""In-memory immutable registry for SEG runtime actions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from seg.actions.build_engine.builder import build_actions
from seg.actions.build_engine.loader import load_module_specs
from seg.actions.build_engine.validator import validate_modules
from seg.actions.exceptions import ActionNotFoundError
from seg.actions.models import ActionSpec


class ActionRegistry:
    """Immutable runtime action registry keyed by fully-qualified action name."""

    def __init__(self, actions: Mapping[str, ActionSpec]) -> None:
        self._actions: dict[str, ActionSpec] = dict(actions)

    def get(self, name: str) -> ActionSpec:
        """Resolve one action by name.

        Raises:
            ActionNotFoundError: If the action name is not present.
        """

        try:
            return self._actions[name]
        except KeyError as exc:
            raise ActionNotFoundError(f"Action not found: {name}") from exc

    def has(self, name: str) -> bool:
        """Return True if the action exists in the registry."""

        return name in self._actions

    def list_names(self) -> tuple[str, ...]:
        """Return deterministic action names."""

        return tuple(sorted(self._actions.keys()))


def build_registry_from_specs(specs_dir: Path) -> ActionRegistry:
    """Build an immutable runtime registry from DSL YAML specs."""

    modules = load_module_specs(specs_dir)
    validate_modules(modules)
    actions = build_actions(modules)
    return ActionRegistry(actions)
