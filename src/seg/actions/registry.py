"""In-memory immutable registry for SEG runtime actions."""

from __future__ import annotations

from collections.abc import Mapping

from seg.actions.build_engine.builder import build_actions
from seg.actions.build_engine.loader import load_module_specs
from seg.actions.build_engine.validator import validate_modules
from seg.actions.engine_config import SPEC_DIRS
from seg.actions.exceptions import ActionNotFoundError
from seg.actions.models import ActionSpec
from seg.actions.models.presentation import ModuleSummary
from seg.actions.presentation.catalog import build_module_summaries
from seg.actions.schemas.module import ModuleSpec
from seg.core.config import Settings, get_settings


class ActionRegistry:
    """Immutable runtime action registry keyed by final runtime action name."""

    def __init__(
        self,
        actions: Mapping[str, ActionSpec],
        modules: list[ModuleSpec],
    ) -> None:
        """Initialize immutable registry state.

        Args:
            actions: Mapping keyed by final runtime action name.
            modules: Loaded module definitions used to build the action map.
        """
        self._actions: dict[str, ActionSpec] = dict(actions)
        self.modules: list[ModuleSpec] = list(modules)

        # Module Presentation cache (build time)
        # Build using detached data structures to avoid circular imports
        # inside the presentation package.
        self.module_summaries: list[ModuleSummary] = build_module_summaries(
            self.modules, self._actions
        )

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
    settings: Settings | None = None,
) -> ActionRegistry:
    """Build an immutable runtime registry from DSL YAML specs."""

    resolved_settings = settings or get_settings()
    modules = load_module_specs(list(SPEC_DIRS), resolved_settings)
    validate_modules(modules)
    actions = build_actions(modules, resolved_settings)
    return ActionRegistry(actions, modules)
