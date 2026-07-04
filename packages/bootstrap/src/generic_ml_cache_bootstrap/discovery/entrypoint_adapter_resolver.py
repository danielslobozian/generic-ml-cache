# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EntryPointAdapterResolver — construct a concrete adapter from its id.

The resolver's counterpart to EntryPointAdapterCatalog: where the catalog reads
``descriptor()`` to answer "what exists?", the resolver constructs the vetted class
to answer "give me the implementation." It resolves ONLY from the catalog's
already-gated classes (X15) — it never enumerates or ``load()``s entry points itself,
so resolving one adapter can no longer run the import-time code of every installed
plugin (a non-whitelisted plugin the catalog gated out is never imported). Local
clients are built with the per-run config; API runners take none.
"""

from __future__ import annotations

from typing import cast

from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_bootstrap.discovery.entrypoint_adapter_catalog import EntryPointAdapterCatalog


class EntryPointAdapterResolver(AdapterResolverPort):
    """Resolve an ``adapter_id`` to a constructed adapter from the catalog's vetted classes."""

    def __init__(self, catalog: EntryPointAdapterCatalog) -> None:
        self._catalog = catalog

    def _class_for(self, adapter_id: str) -> type:
        cls = self._catalog.resolve_class(adapter_id)
        if cls is None:
            raise UnknownClient(f"no adapter for id {adapter_id!r}")
        return cls

    def resolve_local_client(
        self,
        adapter_id: str,
        executable_override: str | None = None,
        timeout: float | None = None,
        stream_path: str | None = None,
    ) -> LocalClientPort:
        cls = self._class_for(adapter_id)
        return cast(
            LocalClientPort,
            cls(executable_override=executable_override, timeout=timeout, stream_path=stream_path),
        )

    def resolve_runner(self, adapter_id: str) -> MlRunnerPort:
        return cast(MlRunnerPort, self._class_for(adapter_id)())
