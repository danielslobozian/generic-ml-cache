# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ExecutionId surrogate identity."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)


def test_generate_returns_an_execution_id_string():
    execution_id = ExecutionId.generate()
    assert isinstance(execution_id, ExecutionId)
    assert isinstance(execution_id, str)
    assert execution_id  # non-empty


def test_generate_is_unique_per_call():
    assert ExecutionId.generate() != ExecutionId.generate()


def test_ml_execution_mints_a_distinct_id_per_instance():
    identity = ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="c",
        prompt_fingerprint="p",
    )
    first = MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
    )
    second = MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
    )
    assert first.execution_id != second.execution_id
