# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CompositeAdapterCatalog — merge several catalogs into one view.

Used by composition to present entry-point adapters and in-process registered
adapters (e.g. test fakes) as a single universe. On an ``adapter_id`` collision
the first catalog wins.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.adapter_catalog_port import AdapterCatalogPort


class CompositeAdapterCatalog(AdapterCatalogPort):
    """An AdapterCatalogPort that unions several catalogs."""

    def __init__(self, catalogs: Iterable[AdapterCatalogPort]) -> None:
        self._catalogs: list[AdapterCatalogPort] = list(catalogs)

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        merged: dict[str, AdapterDescriptor] = {}
        for catalog in self._catalogs:
            for descriptor in catalog.list_adapters():
                merged.setdefault(descriptor.adapter_id, descriptor)
        return list(merged.values())

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        return [d for d in self.list_adapters() if d.client_name == client_name]

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return any(catalog.supports(client_name, mode) for catalog in self._catalogs)
