# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""InMemoryAdapterRegistry — programmatic adapter registration (tests, embedding).

The relocated, infrastructure-layer home of the old ``register()`` seam. Tests
and embedding apps register adapter *classes* here; a composition root then
exposes them as a StaticAdapterCatalog and resolves them. It carries no
packaging-discovery — it is just an in-memory map — so core never needs it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.out.adapter_resolver_port import AdapterResolverPort
from generic_ml_cache_core.application.port.out.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient


class InMemoryAdapterRegistry(AdapterCatalogPort, AdapterResolverPort):
    """A map of adapter classes registered in-process, keyed by ``adapter_id``.

    It is a *live* catalog and resolver in one: composition merges it with the
    entry-point catalog/resolver, and registrations made after that merge are
    still seen (the merge holds this object, not a snapshot)."""

    def __init__(self) -> None:
        self._classes: dict[str, type] = {}

    def register(self, cls: type) -> None:
        """Register an adapter class (must expose a ``descriptor()`` classmethod)."""
        descriptor = cast(AdapterDescriptor, cls.descriptor())  # type: ignore[attr-defined]
        self._classes[descriptor.adapter_id] = cls

    def clear(self) -> None:
        self._classes.clear()

    # ------------------------------------------------------------------
    # AdapterCatalogPort (live view of the registered classes)
    # ------------------------------------------------------------------

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        return [cast(AdapterDescriptor, cls.descriptor()) for cls in self._classes.values()]  # type: ignore[attr-defined]

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        return [d for d in self.list_adapters() if d.client_name == client_name]

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return any(
            d.client_name == client_name and d.supports_mode(mode) for d in self.list_adapters()
        )

    def _class_for(self, adapter_id: str) -> type:
        cls = self._classes.get(adapter_id)
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


#: Process-wide default registry — the relocation of the old module-level
#: ``register()`` global. Composition roots merge it with the entry-point catalog.
_DEFAULT_REGISTRY = InMemoryAdapterRegistry()


def register(cls: type) -> None:
    """Register an adapter class into the process-wide default registry."""
    _DEFAULT_REGISTRY.register(cls)


def default_registry() -> InMemoryAdapterRegistry:
    """Return the process-wide default in-memory registry."""
    return _DEFAULT_REGISTRY
