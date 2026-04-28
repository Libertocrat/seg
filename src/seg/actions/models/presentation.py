"""Public presentation models for SEG action discovery APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ActionSummary:
    """Lightweight public representation of one registered action.

    Attributes:
        action: Short DSL action name, for example "encrypt".
        action_id: Fully qualified runtime action name.
        summary: Optional short summary for discovery views.
        description: Optional long description of the action.
    """

    action: str
    action_id: str
    summary: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class ModuleSummary:
    """Structured public representation of one DSL module.

    Attributes:
        module: Bare module name declared in the DSL YAML.
        module_id: Fully qualified module identifier.
        namespace: Namespace rendered as dot-separated string.
        namespace_path: Namespace segments as a tuple.
        description: Public module description.
        tags: Normalized module tags.
        authors: Optional module authors metadata.
        actions: Discovery summaries for module actions.
    """

    module: str
    module_id: str
    namespace: str
    namespace_path: tuple[str, ...]

    description: str
    tags: tuple[str, ...]
    authors: tuple[str, ...] | None

    actions: list[ActionSummary]


@dataclass(frozen=True, slots=True)
class ActionPublicSpec:
    """Detailed API-facing specification of one action.

    Attributes:
        action: Short DSL action name, for example "encrypt".
        action_id: Fully qualified runtime action name.
        summary: Optional short summary.
        description: Optional long description.
        args: Serialized argument definitions.
        flags: Serialized flag definitions.
        outputs: Serialized output definitions.
        params_schema: JSON schema for the action params model.
        response_schema: JSON schema for execute response payload data.
    """

    action: str
    action_id: str
    summary: str | None
    description: str | None

    args: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    outputs: list[dict[str, Any]]

    params_schema: dict[str, Any]
    response_schema: dict[str, Any]
