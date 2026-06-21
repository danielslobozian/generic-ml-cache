# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionState."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.execution_state import ExecutionState


def test_in_progress_value():
    assert ExecutionState.IN_PROGRESS.value == "in_progress"


def test_success_value():
    assert ExecutionState.SUCCESS.value == "success"


def test_failed_value():
    assert ExecutionState.FAILED.value == "failed"


def test_string_roundtrip():
    for execution_state in ExecutionState:
        assert ExecutionState(execution_state.value) is execution_state


def test_exactly_three_states():
    assert len(ExecutionState) == 3


def test_passthrough_is_not_a_state():
    state_values = {execution_state.value for execution_state in ExecutionState}
    assert "passthrough" not in state_values
