"""Runtime dispatcher for SEG action execution."""

from __future__ import annotations

from typing import Any

from seg.actions.models import ActionExecutionResult
from seg.actions.registry import ActionRegistry
from seg.actions.runtime import executor as runtime_executor
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

    action_spec = registry.get(action_name)
    validated = action_spec.params_model.model_validate(params)
    params_dict = validated.model_dump(mode="python")
    argv = render_command(action_spec, params_dict)
    return await runtime_executor.execute_command(argv, action_spec)
