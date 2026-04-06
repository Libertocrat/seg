"""Runtime dispatcher for SEG action execution."""

from __future__ import annotations

from typing import Any

from seg.actions.models import ActionExecutionResult
from seg.actions.registry import ActionRegistry
from seg.actions.runtime.executor import execute_command
from seg.actions.runtime.renderer import render_command


async def dispatch_action(
    registry: ActionRegistry,
    action_name: str,
    params: dict[str, Any],
) -> ActionExecutionResult:
    """Resolve, validate, render and execute an action.

    This function is intentionally HTTP-agnostic and lets runtime exceptions
    propagate unchanged so they can be translated by the route handler layer.
    """

    spec = registry.get(action_name)
    validated = spec.params_model.model_validate(params)
    params_dict = validated.model_dump(mode="python")
    argv = render_command(spec, params_dict)
    return await execute_command(argv)
