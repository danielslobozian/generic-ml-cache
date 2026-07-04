# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The driver-facing stub-runners hook (W28).

Lets the CLI's no-credential stub mode wire every API client to the in-process
stub adapter without importing that concrete adapter.
"""

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

from generic_ml_cache_bootstrap.discovery.static_adapter_catalog import StaticAdapterCatalog
from generic_ml_cache_bootstrap.stub_runners import stub_api_runners


def _descriptor(client_name: str, boundary: AdapterBoundary) -> AdapterDescriptor:
    mode = ExecutionKind.API if boundary is AdapterBoundary.API else ExecutionKind.LOCAL_MANAGED
    return AdapterDescriptor(
        adapter_id=f"{client_name}.x",
        client_name=client_name,
        boundary=boundary,
        supported_modes=frozenset({mode}),
    )


def test_maps_only_api_clients_to_one_shared_stub():
    catalog = StaticAdapterCatalog(
        [
            _descriptor("claude", AdapterBoundary.API),
            _descriptor("gemini", AdapterBoundary.API),
            _descriptor("claude-cli", AdapterBoundary.LOCAL_CLI),  # excluded
        ]
    )
    runners = stub_api_runners(catalog)
    assert set(runners) == {"claude", "gemini"}
    # One stub instance backs every API client name.
    assert len(set(map(id, runners.values()))) == 1


def test_empty_catalog_yields_no_runners():
    assert stub_api_runners(StaticAdapterCatalog([])) == {}
