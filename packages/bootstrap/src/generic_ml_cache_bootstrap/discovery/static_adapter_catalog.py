# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StaticAdapterCatalog — a catalog over a fixed list of descriptors.

Useful for tests, minimal deployments, and as the in-process half of a composite
(e.g. test fakes registered alongside entry-point adapters). It performs no
discovery; it simply answers questions over the descriptors it was given.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort


class StaticAdapterCatalog(AdapterCatalogPort):
    """An AdapterCatalogPort backed by a predefined list of descriptors."""

    def __init__(self, descriptors: Iterable[AdapterDescriptor] = ()) -> None:
        self._descriptors: list[AdapterDescriptor] = list(descriptors)

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        return list(self._descriptors)

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        return [d for d in self._descriptors if d.client_name == client_name]

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return any(
            d.client_name == client_name and d.supports_mode(mode) for d in self._descriptors
        )
