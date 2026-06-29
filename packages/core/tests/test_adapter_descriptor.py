# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the adapter-catalog domain value objects."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind


def _claude_cli() -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id="claude.cli",
        client_name="claude",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH}),
        capabilities=frozenset({ClientCapability.RUN}),
        display_name="Claude Code",
    )


def test_supports_mode_reflects_supported_modes():
    d = _claude_cli()
    assert d.supports_mode(ExecutionKind.LOCAL_MANAGED) is True
    assert d.supports_mode(ExecutionKind.LOCAL_PASSTHROUGH) is True
    assert d.supports_mode(ExecutionKind.API) is False


def test_has_capability():
    d = _claude_cli()
    assert d.has_capability(ClientCapability.RUN) is True
    assert d.has_capability(ClientCapability.LIST_MODELS) is False


def test_descriptor_is_frozen_and_hashable():
    d = _claude_cli()
    assert {d}  # hashable -> usable in sets/dicts
    assert d == _claude_cli()  # value equality


def test_capabilities_default_to_empty():
    d = AdapterDescriptor(
        adapter_id="x.api",
        client_name="x",
        boundary=AdapterBoundary.API,
        supported_modes=frozenset({ExecutionKind.API}),
    )
    assert d.capabilities == frozenset()
    assert d.priority == 0
    assert d.display_name == ""


def test_boundary_and_capability_enum_values():
    assert AdapterBoundary.LOCAL_CLI.value == "local-cli"
    assert AdapterBoundary.API.value == "api"
    assert ClientCapability.RUN.value == "run"
    assert ClientCapability.LIST_MODELS.value == "list-models"
