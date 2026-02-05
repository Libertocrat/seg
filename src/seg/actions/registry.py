# src/seg/actions/registry.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

# Type variable for the params Pydantic model for an action.
P = TypeVar("P", bound=BaseModel)


# Handler typed to accept a specific Pydantic model instance and return an
# awaitable result. Using a TypeVar keeps strong typing for handlers while
# allowing the registry to store heterogeneously-typed ActionSpec instances.
HandlerFn = Callable[[P], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ActionSpec(Generic[P]):
    """Specification for a registered action.

    - name: action name used by clients
    - params_model: Pydantic model class for input params (type P)
    - handler: async callable that accepts the validated params model (P)
    - result_model: Optional Pydantic model class describing the result
      returned by the handler. When present, the dispatcher will validate
      and normalize handler output against this model.
    """

    name: str
    params_model: type[P]
    handler: HandlerFn
    # Optional result model describing the handler output. When `None`, the
    # dispatcher will return whatever the handler returns without additional
    # Pydantic validation. Making this optional simplifies registering
    # lightweight actions that don't expose a stable result schema.
    result_model: Optional[type[BaseModel]] = None


_REGISTRY: dict[str, ActionSpec[Any]] = {}


def register_action(spec: ActionSpec[Any]) -> None:
    # Explicit allowlist, and refuse duplicates.
    if spec.name in _REGISTRY:
        raise RuntimeError(f"Action already registered: {spec.name}")
    _REGISTRY[spec.name] = spec


def get_action(action_name: str) -> ActionSpec | None:
    return _REGISTRY.get(action_name)


def list_actions() -> list[str]:
    # Useful for debugging / audit endpoints later (optional).
    return sorted(_REGISTRY.keys())
