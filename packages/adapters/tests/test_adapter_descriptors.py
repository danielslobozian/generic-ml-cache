# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Each built-in adapter declares a correct AdapterDescriptor via descriptor()."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

from generic_ml_cache_adapters.discovery.composition import get_adapter


def _descriptor(name):
    return type(get_adapter(name)).descriptor()


def test_local_cli_adapters_descriptors():
    for name, expected_id in (
        ("claude", "claude.cli"),
        ("codex", "codex.cli"),
        ("cursor", "cursor.cli"),
    ):
        d = _descriptor(name)
        assert d.adapter_id == expected_id
        assert d.client_name == name
        assert d.boundary is AdapterBoundary.LOCAL_CLI
        assert d.supported_modes == frozenset(
            {ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH}
        )
        assert ClientCapability.RUN in d.capabilities


def test_only_cursor_lists_models_among_clis():
    assert ClientCapability.LIST_MODELS not in _descriptor("claude").capabilities
    assert ClientCapability.LIST_MODELS not in _descriptor("codex").capabilities
    assert ClientCapability.LIST_MODELS in _descriptor("cursor").capabilities


def test_api_adapters_descriptors():
    for name, expected_id in (
        ("anthropic", "anthropic.api"),
        ("openai", "openai.api"),
        ("gemini", "gemini.api"),
    ):
        d = _descriptor(name)
        assert d.adapter_id == expected_id
        assert d.boundary is AdapterBoundary.API
        assert d.supported_modes == frozenset({ExecutionKind.API})
        assert d.capabilities == frozenset({ClientCapability.RUN, ClientCapability.LIST_MODELS})
