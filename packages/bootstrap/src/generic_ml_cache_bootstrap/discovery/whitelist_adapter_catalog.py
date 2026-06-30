# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""WhitelistAdapterCatalog — restrict a catalog to allowed client names.

Whitelisting is deployment policy, not discovery, so it lives as a composition
wrapper: the daemon wraps the entry-point catalog with this before injecting it,
and core then sees only the permitted universe — it never learns a whitelist exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.adapter_catalog_port import AdapterCatalogPort


class WhitelistAdapterCatalog(AdapterCatalogPort):
    """Expose only the adapters whose client name is in ``allowed_clients``."""

    def __init__(self, inner: AdapterCatalogPort, allowed_clients: Iterable[str]) -> None:
        self._inner = inner
        self._allowed: frozenset[str] = frozenset(allowed_clients)

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        return [d for d in self._inner.list_adapters() if d.client_name in self._allowed]

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        if client_name not in self._allowed:
            return []
        return list(self._inner.find_by_client_name(client_name))

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return client_name in self._allowed and self._inner.supports(client_name, mode)
