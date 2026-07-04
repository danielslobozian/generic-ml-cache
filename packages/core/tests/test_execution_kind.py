# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionKind."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind


def test_local_managed_value():
    assert ExecutionKind.LOCAL_MANAGED.value == "local_managed"


def test_local_passthrough_value():
    assert ExecutionKind.LOCAL_PASSTHROUGH.value == "local_passthrough"


def test_api_value():
    assert ExecutionKind.API.value == "api"


def test_api_passthrough_value():
    assert ExecutionKind.API_PASSTHROUGH.value == "api_passthrough"


def test_string_roundtrip():
    for execution_kind in ExecutionKind:
        assert ExecutionKind(execution_kind.value) is execution_kind


def test_exactly_four_kinds():
    assert len(ExecutionKind) == 4


def test_local_kinds_share_prefix():
    local_kinds = {kind for kind in ExecutionKind if kind.value.startswith("local_")}
    assert local_kinds == {ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH}


def test_api_is_not_local():
    assert not ExecutionKind.API.value.startswith("local_")
