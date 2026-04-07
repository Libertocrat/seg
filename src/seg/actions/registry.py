"""In-memory immutable registry for SEG runtime actions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from seg.actions.build_engine.builder import build_actions
from seg.actions.build_engine.loader import load_module_specs
from seg.actions.build_engine.validator import validate_modules
from seg.actions.exceptions import ActionNotFoundError
from seg.actions.models import ActionSpec
from seg.core.config import Settings, get_settings


class ActionRegistry:
    """Immutable runtime action registry keyed by fully-qualified action name."""

    def __init__(self, actions: Mapping[str, ActionSpec]) -> None:
        """Initialize immutable registry state.

        Args:
            actions: Mapping keyed by fully-qualified action name.
        """
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


def build_registry_from_specs(
    specs_dir: Path,
    settings: Settings | None = None,
) -> ActionRegistry:
    """Build an immutable runtime registry from DSL YAML specs."""

    modules = load_module_specs(specs_dir)
    validate_modules(modules)
    resolved_settings = settings or get_settings()
    actions = build_actions(modules, resolved_settings)
    return ActionRegistry(actions)
