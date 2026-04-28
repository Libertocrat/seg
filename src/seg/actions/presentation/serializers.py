"""Serialization helpers for SEG action presentation models."""

from __future__ import annotations

from typing import Any

from seg.actions.models.core import ActionSpec
from seg.actions.models.presentation import (
    ActionPublicSpec,
    ActionSummary,
    ModuleSummary,
)
from seg.routes.actions.schemas import ExecuteActionData


def to_action_summary(spec: ActionSpec) -> ActionSummary:
    """Convert one runtime action spec into a discovery summary.

    Args:
        spec: Runtime action specification from the registry.

    Returns:
        API-safe action summary model.
    """

    return ActionSummary(
        action=spec.action,
        action_name=spec.name,
        summary=spec.summary,
        description=spec.description,
    )


def to_action_public_spec(spec: ActionSpec) -> ActionPublicSpec:
    """Convert one runtime action spec into a detailed public contract.

    Args:
        spec: Runtime action specification from the registry.

    Returns:
        API-facing detailed action specification.
    """

    args = [
        {
            "name": name,
            "type": arg.type.value,
            "required": arg.required,
            "default": spec.defaults.get(name),
            "constraints": arg.constraints,
            "description": arg.description,
        }
        for name, arg in spec.arg_defs.items()
    ]

    flags = [
        {
            "name": name,
            "default": flag.default,
            "value": flag.value,
            "description": flag.description,
        }
        for name, flag in spec.flag_defs.items()
    ]

    outputs = [
        {
            "name": name,
            "type": out.type.value,
            "source": out.source.value,
            "description": out.description,
        }
        for name, out in spec.outputs.items()
    ]

    return ActionPublicSpec(
        name=spec.name,
        summary=spec.summary,
        description=spec.description,
        args=args,
        flags=flags,
        outputs=outputs,
        params_schema=spec.params_model.model_json_schema(),
        response_schema=ExecuteActionData.model_json_schema(),
    )


def module_summary_to_dict(module: ModuleSummary) -> dict[str, Any]:
    """Convert one module summary model into API response shape.

    Args:
        module: Public module summary model.

    Returns:
        Dictionary payload compatible with JSON responses.
    """

    return {
        "module": module.module,
        "module_id": module.module_id,
        "namespace": module.namespace,
        "namespace_path": list(module.namespace_path),
        "description": module.description,
        "tags": list(module.tags),
        "authors": list(module.authors or []),
        "actions": [
            {
                "action": action.action,
                "action_name": action.action_name,
                "summary": action.summary,
                "description": action.description,
            }
            for action in module.actions
        ],
    }


def modules_to_response(modules: list[ModuleSummary]) -> dict[str, Any]:
    """Convert module summaries into the discovery response payload.

    Args:
        modules: Public module summaries.

    Returns:
        Root dictionary payload for module discovery endpoints.
    """

    return {"modules": [module_summary_to_dict(module) for module in modules]}
