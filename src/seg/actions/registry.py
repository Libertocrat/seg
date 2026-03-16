"""In-memory registry for SEG action specifications."""

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
    """Specification object describing a registered SEG action.

    An ActionSpec defines both the runtime behavior and the documentation
    metadata of an action that can be executed via `/v1/execute`.

    Each action is resolved dynamically by the dispatcher using the `name`
    field. The dispatcher validates the incoming `params` against
    `params_model`, invokes the `handler`, and optionally validates the
    returned result against `result_model`.

    In addition to execution metadata, ActionSpec also carries optional
    OpenAPI documentation metadata that is used during dynamic schema
    generation. This allows SEG to expose rich, runtime-aware API
    documentation without coupling route definitions to individual actions.

    Attributes:
        name:
            Unique action identifier used by clients in the `action` field
            of the `/v1/execute` request body.

        params_model:
            Pydantic model class describing the validated structure of the
            `params` field for this action.

        handler:
            Async callable that receives an instance of `params_model` and
            performs the action logic. It must return either a plain dict
            or an instance compatible with `result_model` (if provided).

        result_model:
            Optional Pydantic model class describing the normalized result
            schema returned by the handler. When provided, the dispatcher
            validates and serializes the handler output against this model
            before embedding it into the ResponseEnvelope. When None,
            the raw handler output is returned as-is.

        summary:
            Optional short description used as a concise title for this
            action in generated OpenAPI documentation. Intended for
            one-line display in UI tools like Swagger.

        description:
            Optional extended description of the action. This can include
            behavioral notes, security constraints, edge-case behavior,
            or execution guarantees. Used when dynamically generating
            enriched documentation for `/v1/execute`.

        tags:
            Optional tuple of tags associated with the action. These may
            be used to group or classify actions in documentation or
            tooling layers. While `/v1/execute` remains a single endpoint,
            tags can be leveraged for logical grouping in future tooling.

        deprecated:
            Indicates whether the action is deprecated. When True, the
            generated OpenAPI schema may mark this action as deprecated,
            signaling clients to migrate away from it.

        params_example:
            Optional example instance of `params_model` used to generate
            OpenAPI request examples.

        result_example:
            Optional example instance of `result_model` used to generate
            OpenAPI 200 response examples.
    """

    # ------------------------------------------------------------------
    # Core execution metadata
    # ------------------------------------------------------------------

    name: str
    params_model: type[P]
    handler: "HandlerFn"
    result_model: Optional[type[BaseModel]] = None

    # ------------------------------------------------------------------
    # Optional OpenAPI documentation metadata
    # ------------------------------------------------------------------

    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    deprecated: bool = False

    # ------------------------------------------------------------------
    # Optional OpenAPI example payloads (strongly typed)
    # ------------------------------------------------------------------

    params_example: P | None = None
    result_example: BaseModel | None = None


_REGISTRY: dict[str, ActionSpec[Any]] = {}


def register_action(spec: ActionSpec[Any]) -> None:
    """Register a new action specification.

    Args:
        spec: Fully defined action specification to add to the allowlist.

    Raises:
        TypeError: If example payloads do not match their declared models.
        RuntimeError: If another action is already registered with the same name.
    """

    # Validate OpenAPI request/response examples
    if spec.params_example is not None and spec.params_model:
        if not isinstance(spec.params_example, spec.params_model):
            raise TypeError(
                f"Example params for action '{spec.name}' must be instance of "
                f"{spec.params_model.__name__}"
            )
    if spec.result_example is not None and spec.result_model:
        if not isinstance(spec.result_example, spec.result_model):
            raise TypeError(
                f"Example result for action '{spec.name}' must be instance of "
                f"{spec.result_model.__name__}"
            )

    # Explicit allowlist, and refuse duplicates.
    if spec.name in _REGISTRY:
        raise RuntimeError(f"Action already registered: {spec.name}")
    _REGISTRY[spec.name] = spec


def get_action(action_name: str) -> ActionSpec | None:
    """Return a registered action by name.

    Args:
        action_name: Client-visible action identifier.

    Returns:
        The matching action specification, or `None` if it is not registered.
    """

    return _REGISTRY.get(action_name)


def list_actions() -> list[str]:
    """List all registered action names in sorted order.

    Returns:
        Sorted action names currently present in the registry.
    """

    # Useful for debugging / audit endpoints later (optional).
    return sorted(_REGISTRY.keys())


# Public helpers for safe runtime manipulation / inspection of the registry.
def get_registry_snapshot() -> dict[str, ActionSpec[Any]]:
    """Return a shallow copy of the current registry mapping.

    Tests and runtime management code can use this to take a snapshot
    without holding a reference to the internal dict.
    """
    return _REGISTRY.copy()


def replace_registry(new_registry: dict[str, ActionSpec[Any]]) -> None:
    """Replace the internal registry object with `new_registry`.

    This performs a rebinding of the module-level name so callers do not
    need to reach into `_REGISTRY` directly. Use with care: callers should
    keep a snapshot if they intend to restore the previous state.
    """
    global _REGISTRY
    _REGISTRY = new_registry


def clear_registry() -> None:
    """Clear all registered actions from the active registry.

    Prefer `replace_registry({})` when you need to swap the object
    reference instead of mutating in-place.
    """
    _REGISTRY.clear()


def restore_registry(snapshot: dict[str, ActionSpec[Any]]) -> None:
    """Restore a previously-captured registry snapshot by rebinding the
    internal registry name to the provided snapshot.
    """
    # This is a convenience wrapper around `replace_registry` to clarify intent
    replace_registry(snapshot)
