"""
Unit tests for the SEG action dispatcher.

These tests freeze dispatcher invariants:
- correct action lookup and dispatch
- stable error envelopes for all failure modes
- strict input validation
- safe handling of handler-level and unexpected errors
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from seg.actions.dispatcher import dispatch_execute
from seg.actions.exceptions import SegActionError
from seg.actions.registry import ActionSpec, register_action
from seg.core.errors import (
    ACTION_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_RESULT,
    TIMEOUT,
    ErrorDef,
)
from seg.core.schemas.envelope import ResponseEnvelope
from seg.core.schemas.execute import ExecuteRequest

# ============================================================================
# Test helpers
# ============================================================================


class DummyActionParams(BaseModel):
    """Valid params model for dispatcher tests."""

    value: int


class DummyActionResult(BaseModel):
    """Valid result model for dispatcher tests."""

    doubled: int


async def ok_handler(params: DummyActionParams):
    """Handler that returns a valid result."""
    return {"doubled": params.value * 2}


async def invalid_result_handler(params: DummyActionParams):
    """Handler that returns an invalid result shape."""
    return {"wrong": "shape"}


async def seg_error_handler(params: DummyActionParams):
    """Handler that raises a controlled SegActionError."""
    custom_error = ErrorDef(
        code="CUSTOM_ERROR",
        http_status=418,
        default_message="Controlled failure",
    )
    raise SegActionError(
        custom_error,
        "Controlled failure",
        details={"value": params.value},
    )


async def timeout_handler(params: DummyActionParams):
    """Handler that simulates a timeout."""
    raise TimeoutError("simulated timeout")


async def unexpected_error_handler(params: DummyActionParams):
    """Handler that raises an unexpected exception."""
    raise RuntimeError("boom")


def make_request(action: str, params: dict) -> ExecuteRequest:
    """Helper to build ExecuteRequest instances."""
    return ExecuteRequest(action=action, params=params)


# ============================================================================
# Action lookup
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_unknown_action_returns_failure_envelope():
    """
    GIVEN no action registered under the requested name
    WHEN dispatch_execute is called
    THEN a failure ResponseEnvelope with ACTION_NOT_FOUND is returned
    """
    req = make_request("missing_action", {"value": 1})

    response, status = await dispatch_execute(req)

    assert isinstance(response, ResponseEnvelope)
    assert status == 404
    assert response.success is False
    assert response.error.code == ACTION_NOT_FOUND.code
    assert response.error.details["action"] == "missing_action"


# ============================================================================
# Params validation
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_invalid_params_returns_failure_envelope(clean_action_registry):
    """
    GIVEN a registered action
    WHEN params do not conform to the action params model
    THEN a failure ResponseEnvelope with INVALID_PARAMS is returned
    """
    register_action(
        ActionSpec(
            name="validate_params",
            params_model=DummyActionParams,
            handler=ok_handler,
            result_model=DummyActionResult,
        )
    )

    req = make_request("validate_params", {"value": "not-an-int"})

    response, status = await dispatch_execute(req)

    assert status == 400
    assert response.success is False
    assert response.error.code == INVALID_PARAMS.code
    assert "errors" in response.error.details


# ============================================================================
# Successful dispatch
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_success_with_result_model(clean_action_registry):
    """
    GIVEN a registered action with a result_model
    WHEN the handler executes successfully
    THEN a success ResponseEnvelope with validated data is returned
    """
    register_action(
        ActionSpec(
            name="ok_action",
            params_model=DummyActionParams,
            handler=ok_handler,
            result_model=DummyActionResult,
        )
    )

    req = make_request("ok_action", {"value": 3})

    response, status = await dispatch_execute(req)

    assert status == 200
    assert response.success is True
    assert isinstance(response.data, DummyActionResult)
    assert response.data.doubled == 6


@pytest.mark.asyncio
async def test_dispatch_success_without_result_model(clean_action_registry):
    """
    GIVEN a registered action without a result_model
    WHEN the handler executes successfully
    THEN a success ResponseEnvelope with raw data is returned
    """
    register_action(
        ActionSpec(
            name="raw_action",
            params_model=DummyActionParams,
            handler=ok_handler,
            result_model=None,
        )
    )

    req = make_request("raw_action", {"value": 2})

    response, status = await dispatch_execute(req)

    assert status == 200
    assert response.success is True
    assert response.data == {"doubled": 4}


# ============================================================================
# Result validation
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_invalid_result_returns_failure_envelope(clean_action_registry):
    """
    GIVEN a registered action with a result_model
    WHEN the handler returns an invalid result
    THEN a failure ResponseEnvelope with INVALID_RESULT is returned
    """
    register_action(
        ActionSpec(
            name="bad_result",
            params_model=DummyActionParams,
            handler=invalid_result_handler,
            result_model=DummyActionResult,
        )
    )

    req = make_request("bad_result", {"value": 1})

    response, status = await dispatch_execute(req)

    assert status == 500
    assert response.success is False
    assert response.error.code == INVALID_RESULT.code
    assert "errors" in response.error.details


# ============================================================================
# Error propagation
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_seg_action_error_is_propagated_cleanly(clean_action_registry):
    """
    GIVEN a handler that raises SegActionError
    WHEN dispatch_execute is called
    THEN the error is propagated as a structured failure envelope
    """
    register_action(
        ActionSpec(
            name="seg_error",
            params_model=DummyActionParams,
            handler=seg_error_handler,
        )
    )

    req = make_request("seg_error", {"value": 5})

    response, status = await dispatch_execute(req)

    assert status == 418
    assert response.success is False
    assert response.error.code == "CUSTOM_ERROR"
    assert response.error.message == "Controlled failure"
    assert response.error.details == {"value": 5}


@pytest.mark.asyncio
async def test_dispatch_timeout_error_returns_timeout_failure(clean_action_registry):
    """
    GIVEN a handler that raises TimeoutError
    WHEN dispatch_execute is called
    THEN a TIMEOUT failure ResponseEnvelope is returned
    """
    register_action(
        ActionSpec(
            name="timeout_action",
            params_model=DummyActionParams,
            handler=timeout_handler,
        )
    )

    req = make_request("timeout_action", {"value": 1})

    response, status = await dispatch_execute(req)

    assert status == 504
    assert response.success is False
    assert response.error.code == TIMEOUT.code


@pytest.mark.asyncio
async def test_dispatch_unexpected_error_returns_internal_error(clean_action_registry):
    """
    GIVEN a handler that raises an unexpected exception
    WHEN dispatch_execute is called
    THEN an INTERNAL_ERROR failure ResponseEnvelope is returned
    """
    register_action(
        ActionSpec(
            name="boom_action",
            params_model=DummyActionParams,
            handler=unexpected_error_handler,
        )
    )

    req = make_request("boom_action", {"value": 1})

    response, status = await dispatch_execute(req)

    assert status == 500
    assert response.success is False
    assert response.error.code == INTERNAL_ERROR.code
