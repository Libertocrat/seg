# tests/test_schemas_execute.py
"""
Tests for ExecuteRequest schema.

These tests define and freeze the input contract for execution requests
handled by SEG. They focus on schema invariants, not action behavior.
"""

import pytest
from pydantic import ValidationError

from seg.routes.actions.schemas import ExecuteRequest

# ============================================================================
# Success Cases
# ============================================================================


def test_execute_request_valid_minimal_payload():
    """
    GIVEN a minimal valid execution request payload
    WHEN the ExecuteRequest schema is validated
    THEN the model is created successfully with expected values
    """
    req = ExecuteRequest(action="noop")

    assert req.action == "noop"
    assert req.params == {}


def test_execute_request_accepts_params_dict():
    """
    GIVEN a valid execution request with params
    WHEN the ExecuteRequest schema is validated
    THEN params are preserved as-is
    """
    params = {"path": "/uploads/file.txt", "algorithm": "sha256"}

    req = ExecuteRequest(action="file_checksum", params=params)

    assert req.action == "file_checksum"
    assert req.params == params


def test_execute_request_accepts_empty_params_by_default():
    """
    GIVEN a valid execution request without params
    WHEN the ExecuteRequest schema is validated
    THEN params defaults to an empty dictionary
    """
    req = ExecuteRequest(action="noop")

    assert req.action == "noop"
    assert req.params == {}


# ============================================================================
# Required fields
# ============================================================================


def test_execute_request_missing_action_raises():
    """
    GIVEN an execution request missing the required 'action' field
    WHEN the ExecuteRequest schema is validated
    THEN a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        ExecuteRequest()


# ============================================================================
# Field type validation
# ============================================================================


def test_execute_request_action_must_be_string():
    """
    GIVEN an execution request where 'action' is not a string
    WHEN the ExecuteRequest schema is validated
    THEN a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        ExecuteRequest(action=123)


def test_execute_request_params_must_be_dict():
    """
    GIVEN an execution request where 'params' is not a dict
    WHEN the ExecuteRequest schema is validated
    THEN a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        ExecuteRequest(action="noop", params=["not", "a", "dict"])


# ============================================================================
# Contract shape invariants
# ============================================================================


def test_execute_request_has_stable_shape():
    """
    GIVEN a valid ExecuteRequest
    WHEN the model is instantiated
    THEN fields 'action' and 'params' always exist
    """
    req = ExecuteRequest(action="noop")

    assert hasattr(req, "action")
    assert hasattr(req, "params")
