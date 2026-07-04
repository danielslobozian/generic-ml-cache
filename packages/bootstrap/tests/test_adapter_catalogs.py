# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the adapter catalogs (infrastructure discovery)."""

from __future__ import annotations

import pytest
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

from generic_ml_cache_bootstrap.discovery import entrypoint_adapter_catalog as epc_module
from generic_ml_cache_bootstrap.discovery.entrypoint_adapter_catalog import EntryPointAdapterCatalog
from generic_ml_cache_bootstrap.discovery.static_adapter_catalog import StaticAdapterCatalog

# --- StaticAdapterCatalog ----------------------------------------------------


def _descriptor(client_name, mode):
    return AdapterDescriptor(
        adapter_id=f"{client_name}.x",
        client_name=client_name,
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({mode}),
    )


def test_static_catalog_answers_over_its_list():
    catalog = StaticAdapterCatalog([_descriptor("claude", ExecutionKind.LOCAL_MANAGED)])
    assert [d.client_name for d in catalog.list_adapters()] == ["claude"]
    assert [d.adapter_id for d in catalog.find_by_client_name("claude")] == ["claude.x"]
    assert catalog.find_by_client_name("absent") == []
    assert catalog.supports("claude", ExecutionKind.LOCAL_MANAGED) is True
    assert catalog.supports("claude", ExecutionKind.API) is False


# --- EntryPointAdapterCatalog against the real installed adapters ------------


def test_entrypoint_catalog_discovers_builtin_adapters():
    catalog = EntryPointAdapterCatalog()
    ids = {d.adapter_id for d in catalog.list_adapters()}
    assert {"claude.cli", "codex.cli", "cursor.cli"} <= ids
    assert {"anthropic.api", "openai.api", "gemini.api"} <= ids


def test_entrypoint_catalog_find_and_supports():
    catalog = EntryPointAdapterCatalog()
    assert [d.adapter_id for d in catalog.find_by_client_name("claude")] == ["claude.cli"]
    assert catalog.supports("claude", ExecutionKind.LOCAL_PASSTHROUGH) is True
    assert catalog.supports("claude", ExecutionKind.API) is False
    assert catalog.supports("anthropic", ExecutionKind.API) is True


def test_entrypoint_catalog_sources_map_ids_to_packages():
    catalog = EntryPointAdapterCatalog()
    sources = catalog.sources()
    assert "claude.cli" in sources
    assert "generic-ml-cache-adapters" in sources["claude.cli"]


# --- graceful handling of broken / incompatible entry points -----------------


class _FakeDist:
    def __init__(self, name):
        self.metadata = {"Name": name, "Version": "1.0"}
        self.name = name
        self.version = "1.0"


class _FakeEntryPoint:
    # Defaults to the bundled (trusted) distribution so the broken/descriptor/
    # version tests exercise the load path; the trust-gate tests override it.
    def __init__(self, name, loader, dist_name="generic-ml-cache-adapters"):
        self.name = name
        self._loader = loader
        self.dist = _FakeDist(dist_name)

    def load(self):
        return self._loader()


def test_broken_entry_point_is_skipped_with_warning(monkeypatch):
    def _boom():
        raise ImportError("kaboom")

    monkeypatch.setattr(
        epc_module, "iter_entry_points", lambda group: [_FakeEntryPoint("bad", _boom)]
    )
    catalog = EntryPointAdapterCatalog()
    with pytest.warns(UserWarning):
        assert catalog.list_adapters() == []


def test_entry_point_without_descriptor_is_skipped(monkeypatch):
    class _NoDescriptor:
        name = "x"

    monkeypatch.setattr(
        epc_module,
        "iter_entry_points",
        lambda group: [_FakeEntryPoint("nd", lambda: _NoDescriptor)],
    )
    catalog = EntryPointAdapterCatalog()
    with pytest.warns(UserWarning):
        assert catalog.list_adapters() == []


def test_incompatible_contract_version_is_skipped(monkeypatch):
    class _FutureAdapter:
        name = "future"
        adapter_contract_version = "99"

        @classmethod
        def descriptor(cls):  # pragma: no cover - never reached, version gate first
            raise AssertionError("should not be called")

    monkeypatch.setattr(
        epc_module,
        "iter_entry_points",
        lambda group: [_FakeEntryPoint("future", lambda: _FutureAdapter)],
    )
    catalog = EntryPointAdapterCatalog()
    with pytest.warns(UserWarning):
        assert catalog.list_adapters() == []


# --- load-time trust gate (G1) -----------------------------------------------


class _AcmeAdapter:
    name = "acme"

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.api("acme", (), "Acme")


def test_untrusted_third_party_plugin_is_never_loaded(monkeypatch):
    loaded = {"called": False}

    def _loader():
        loaded["called"] = True
        return _AcmeAdapter

    monkeypatch.setattr(
        epc_module,
        "iter_entry_points",
        lambda group: [_FakeEntryPoint("acme", _loader, dist_name="acme-sdk")],
    )
    catalog = EntryPointAdapterCatalog()  # no whitelist -> safe default
    assert catalog.list_adapters() == []
    # The gate is BEFORE ep.load(): the plugin's module code never runs.
    assert loaded["called"] is False


def test_third_party_plugin_loads_only_when_whitelisted(monkeypatch):
    monkeypatch.setattr(
        epc_module,
        "iter_entry_points",
        lambda group: [_FakeEntryPoint("acme", lambda: _AcmeAdapter, dist_name="acme-sdk")],
    )
    catalog = EntryPointAdapterCatalog(whitelist=frozenset({"acme"}))
    assert [d.client_name for d in catalog.list_adapters()] == ["acme"]


def test_bundled_distribution_loads_without_a_whitelist(monkeypatch):
    monkeypatch.setattr(
        epc_module,
        "iter_entry_points",
        lambda group: [_FakeEntryPoint("acme", lambda: _AcmeAdapter)],  # trusted dist
    )
    catalog = EntryPointAdapterCatalog()
    assert [d.client_name for d in catalog.list_adapters()] == ["acme"]
