# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the adapter resolvers (id -> constructed adapter)."""

from __future__ import annotations

import sys

import pytest
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_adapters.discovery.entrypoint_adapter_resolver import (
    EntryPointAdapterResolver,
)
from generic_ml_cache_adapters.discovery.in_memory_adapter_registry import InMemoryAdapterRegistry

# --- EntryPointAdapterResolver against the real installed adapters -----------


def test_resolve_local_client_constructs_the_adapter():
    resolver = EntryPointAdapterResolver()
    client = resolver.resolve_local_client("claude.cli", timeout=5.0)
    assert (
        client.client_name == "claude"
        if hasattr(client, "client_name")
        else client.name == "claude"
    )
    assert callable(client.execute_managed)


def test_resolve_runner_constructs_an_api_adapter():
    resolver = EntryPointAdapterResolver()
    runner = resolver.resolve_runner("anthropic.api")
    assert runner.name == "anthropic"
    assert callable(runner.run)


def test_resolve_unknown_id_raises():
    resolver = EntryPointAdapterResolver()
    with pytest.raises(UnknownClient):
        resolver.resolve_local_client("nope.cli")


# --- InMemoryAdapterRegistry -------------------------------------------------


class _FakeLocal:
    name = "memfake"
    default_executable = sys.executable

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        self.timeout = timeout

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor(
            adapter_id="memfake.cli",
            client_name="memfake",
            boundary=AdapterBoundary.LOCAL_CLI,
            supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED}),
        )


def test_in_memory_registry_is_a_live_catalog():
    registry = InMemoryAdapterRegistry()
    registry.register(_FakeLocal)
    assert [d.adapter_id for d in registry.list_adapters()] == ["memfake.cli"]
    assert registry.supports("memfake", ExecutionKind.LOCAL_MANAGED) is True
    assert registry.supports("memfake", ExecutionKind.API) is False


def test_in_memory_registry_resolves_with_config():
    registry = InMemoryAdapterRegistry()
    registry.register(_FakeLocal)
    client = registry.resolve_local_client("memfake.cli", timeout=9.0)
    assert isinstance(client, _FakeLocal)
    assert client.timeout == 9.0


def test_in_memory_registry_unknown_raises():
    registry = InMemoryAdapterRegistry()
    with pytest.raises(UnknownClient):
        registry.resolve_local_client("missing.cli")
