"""
Unit tests for the SEG runtime dispatcher.

These tests freeze dispatcher invariants for the DSL runtime architecture:
- action resolution through immutable registry
- strict params validation through generated params models
- pure runtime result contract (ActionExecutionResult)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from seg.actions.dispatcher import dispatch_action
from seg.actions.exceptions import ActionNotFoundError
from seg.actions.models import ActionExecutionResult

# ============================================================================
# Runtime Dispatch
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_action_success(valid_registry):
    """
    GIVEN a valid registry and a known action without required params
    WHEN dispatch_action is called
    THEN an ActionExecutionResult with process outputs is returned
    """
    result = await dispatch_action(
        valid_registry,
        "test_runtime.ping",
        {},
    )

    assert isinstance(result, ActionExecutionResult)
    assert result.returncode == 0
    assert isinstance(result.stdout, bytes)
    assert b"hello" in result.stdout


@pytest.mark.asyncio
async def test_dispatch_action_unknown_raises(valid_registry):
    """
    GIVEN a valid registry
    WHEN dispatch_action is called with an unknown action name
    THEN ActionNotFoundError is raised
    """
    with pytest.raises(ActionNotFoundError):
        await dispatch_action(valid_registry, "test_runtime.unknown", {})


@pytest.mark.asyncio
async def test_dispatch_action_invalid_params(valid_registry):
    """
    GIVEN a known action with a required integer argument
    WHEN dispatch_action receives params with an invalid type
    THEN a Pydantic ValidationError is raised
    """
    with pytest.raises(ValidationError):
        await dispatch_action(
            valid_registry,
            "test_runtime.repeat",
            {"count": "not-an-int"},
        )
