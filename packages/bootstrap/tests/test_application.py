# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for build_application_api — the shared composition root."""

import sqlite3
from typing import cast

from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_bootstrap.application import build_application_api


def _conn_factory(db_path):
    def _connect() -> DbConnection:
        return cast(DbConnection, sqlite3.connect(str(db_path), check_same_thread=False))

    return _connect


def _no_runners(
    _catalog: AdapterCatalogPort, _resolver: AdapterResolverPort
) -> dict[str, RegisteredAdapterPort]:
    return {}


def test_build_application_api_wires_the_full_graph(tmp_path):
    api = build_application_api(
        _conn_factory(tmp_path / "executions.sqlite3"),
        tmp_path,
        _no_runners,
    )
    assert isinstance(api, ApplicationApi)
    # Every field is a wired inbound port — spot-check across the capabilities,
    # including a segregated purge operation and one that shares its service.
    assert api.run_ml is not None
    assert api.probe is not None
    assert api.run_gateway is not None
    assert api.purge_by_key is not None
    assert api.evict_to_quota is not None
    assert api.tag_session is not None
    assert api.list_execution_summaries is not None
    assert api.read_artifact_blob is not None


def test_build_application_api_runs_migrations(tmp_path):
    # A second build over the same store must not fail — migrations are idempotent.
    db_path = tmp_path / "executions.sqlite3"
    build_application_api(_conn_factory(db_path), tmp_path, _no_runners)
    api = build_application_api(_conn_factory(db_path), tmp_path, _no_runners)
    assert isinstance(api, ApplicationApi)
    assert db_path.exists()


def test_build_runners_receives_catalog_and_resolver(tmp_path):
    seen: dict[str, object] = {}

    def _runners(
        catalog: AdapterCatalogPort, resolver: AdapterResolverPort
    ) -> dict[str, RegisteredAdapterPort]:
        seen["catalog"] = catalog
        seen["resolver"] = resolver
        return {}

    build_application_api(_conn_factory(tmp_path / "executions.sqlite3"), tmp_path, _runners)
    assert seen["catalog"] is not None
    assert seen["resolver"] is not None
