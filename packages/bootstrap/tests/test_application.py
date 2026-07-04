# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for build_application_api — the shared composition root."""

from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_bootstrap.application import build_application_api


def _no_runners(
    _catalog: AdapterCatalogPort, _resolver: AdapterResolverPort
) -> dict[str, RegisteredAdapterPort]:
    return {}


def test_build_application_api_wires_the_full_graph(tmp_path):
    # No persistence injected -> the default SQLite backend is built under store_root.
    api = build_application_api(tmp_path, _no_runners)
    assert isinstance(api, ApplicationApi)
    # Every field is a wired inbound port — spot-check across the capabilities,
    # including a segregated purge operation and one that shares its service.
    assert api.run_ml is not None
    assert api.probe is not None
    assert api.purge_by_key is not None
    assert api.evict_to_quota is not None
    assert api.tag_session is not None
    assert api.list_execution_summaries is not None
    assert api.read_artifact_blob is not None
    assert api.repair_store is not None


def test_build_application_api_runs_migrations(tmp_path):
    # A second build over the same store must not fail — migrations are idempotent.
    build_application_api(tmp_path, _no_runners)
    api = build_application_api(tmp_path, _no_runners)
    assert isinstance(api, ApplicationApi)
    assert (tmp_path / "executions.sqlite3").exists()


def test_build_runners_receives_catalog_and_resolver(tmp_path):
    seen: dict[str, object] = {}

    def _runners(
        catalog: AdapterCatalogPort, resolver: AdapterResolverPort
    ) -> dict[str, RegisteredAdapterPort]:
        seen["catalog"] = catalog
        seen["resolver"] = resolver
        return {}

    build_application_api(tmp_path, _runners)
    assert seen["catalog"] is not None
    assert seen["resolver"] is not None


def test_injected_persistence_backend_overrides_the_default(tmp_path):
    # An embedder injects their own backend; the default SQLite one is not built.
    from generic_ml_cache_bootstrap.persistence_backend import sqlite_persistence_backend

    backend = sqlite_persistence_backend(tmp_path / "custom.sqlite3")
    api = build_application_api(tmp_path, _no_runners, persistence=backend)
    assert isinstance(api, ApplicationApi)
    assert (tmp_path / "custom.sqlite3").exists()  # the injected backend was used + migrated
    assert not (tmp_path / "executions.sqlite3").exists()  # the default was NOT built


class _FakeBlobStore(BlobStorePort):
    def get(self, key):
        return None

    def put(self, key, output):
        pass

    def is_healthy(self):
        return True

    def remove(self, key):
        pass


def test_injected_blob_store_skips_filesystem_encryption_recovery(tmp_path, monkeypatch):
    # X20: an embedder injecting its own blob store (Postgres/S3) owns its own recovery,
    # so bootstrap must NOT run the hardcoded filesystem encryption recovery — it would
    # read/write/lock local FS encryption state under a nominal store_root.
    import generic_ml_cache_bootstrap.application as app_module

    calls: list = []
    monkeypatch.setattr(app_module, "recover_store", lambda root: calls.append(root))
    build_application_api(tmp_path, _no_runners, blob_store=_FakeBlobStore())
    assert calls == []


def test_default_filesystem_stack_runs_encryption_recovery(tmp_path, monkeypatch):
    import generic_ml_cache_bootstrap.application as app_module

    calls: list = []
    monkeypatch.setattr(app_module, "recover_store", lambda root: calls.append(root))
    build_application_api(tmp_path, _no_runners)  # no blob store injected → default FS stack
    assert calls == [tmp_path]
