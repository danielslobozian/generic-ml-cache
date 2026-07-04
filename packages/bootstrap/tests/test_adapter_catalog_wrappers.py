# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the composite/whitelist catalog wrappers and composite resolver."""

from __future__ import annotations

import pytest
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_bootstrap.discovery.composite_adapter_catalog import CompositeAdapterCatalog
from generic_ml_cache_bootstrap.discovery.composite_adapter_resolver import CompositeAdapterResolver
from generic_ml_cache_bootstrap.discovery.static_adapter_catalog import StaticAdapterCatalog


def _d(client_name, adapter_id=None):
    return AdapterDescriptor(
        adapter_id=adapter_id or f"{client_name}.cli",
        client_name=client_name,
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED}),
    )


# --- CompositeAdapterCatalog -------------------------------------------------


def test_composite_unions_catalogs():
    a = StaticAdapterCatalog([_d("claude")])
    b = StaticAdapterCatalog([_d("cursor")])
    composite = CompositeAdapterCatalog([a, b])
    assert {d.client_name for d in composite.list_adapters()} == {"claude", "cursor"}
    assert composite.supports("cursor", ExecutionKind.LOCAL_MANAGED) is True


def test_composite_first_wins_on_id_collision():
    primary = StaticAdapterCatalog([_d("claude", "claude.cli")])
    other = AdapterDescriptor(
        adapter_id="claude.cli",
        client_name="claude",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.API}),  # different, to detect which wins
    )
    composite = CompositeAdapterCatalog([primary, StaticAdapterCatalog([other])])
    got = [d for d in composite.list_adapters() if d.adapter_id == "claude.cli"]
    assert len(got) == 1
    assert got[0].supported_modes == frozenset({ExecutionKind.LOCAL_MANAGED})  # primary won


# --- CompositeAdapterResolver ------------------------------------------------


class _Resolver:
    def __init__(self, known_id):
        self._known = known_id

    def resolve_local_client(
        self, adapter_id, executable_override=None, timeout=None, stream_path=None
    ):
        if adapter_id != self._known:
            raise UnknownClient(adapter_id)
        return f"local:{adapter_id}"

    def resolve_runner(self, adapter_id):
        if adapter_id != self._known:
            raise UnknownClient(adapter_id)
        return f"runner:{adapter_id}"


def test_composite_resolver_uses_first_that_succeeds():
    resolver = CompositeAdapterResolver([_Resolver("a.cli"), _Resolver("b.cli")])
    assert resolver.resolve_local_client("b.cli") == "local:b.cli"
    assert resolver.resolve_runner("a.cli") == "runner:a.cli"


def test_composite_resolver_unknown_everywhere_raises():
    resolver = CompositeAdapterResolver([_Resolver("a.cli")])
    with pytest.raises(UnknownClient):
        resolver.resolve_local_client("z.cli")
