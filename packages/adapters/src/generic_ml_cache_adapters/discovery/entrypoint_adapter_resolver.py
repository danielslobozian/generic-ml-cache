# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EntryPointAdapterResolver — construct a concrete adapter from its id.

The resolver's counterpart to EntryPointAdapterCatalog: where the catalog reads
``descriptor()`` to answer "what exists?", the resolver loads the class and
constructs it to answer "give me the implementation." Local clients are built
with the per-run config; API runners take none.
"""

from __future__ import annotations

from typing import cast

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.port.out.adapter_resolver_port import AdapterResolverPort
from generic_ml_cache_core.application.port.out.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_adapters.discovery._entrypoints import (
    ADAPTER_ENTRYPOINT_GROUP,
    iter_entry_points,
)


class EntryPointAdapterResolver(AdapterResolverPort):
    """Resolve an ``adapter_id`` to a constructed adapter via the entry points."""

    def __init__(self, group: str = ADAPTER_ENTRYPOINT_GROUP) -> None:
        self._group = group
        self._by_id: dict[str, type] | None = None

    def _classes(self) -> dict[str, type]:
        if self._by_id is None:
            mapping: dict[str, type] = {}
            for ep in iter_entry_points(self._group):
                try:
                    cls = ep.load()
                    describe = getattr(cls, "descriptor", None)
                    if not callable(describe):
                        continue
                    descriptor = cast(AdapterDescriptor, describe())
                except Exception:  # noqa: BLE001 — EntryPointAdapterCatalog already warns
                    continue
                mapping[descriptor.adapter_id] = cls
            self._by_id = mapping
        return self._by_id

    def _class_for(self, adapter_id: str) -> type:
        cls = self._classes().get(adapter_id)
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
