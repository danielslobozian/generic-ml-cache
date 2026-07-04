# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SelectAdapterForExecutionService — pick the adapter for a client + mode.

Selection is application logic (it applies rules: filter by client, mode, then
required capabilities, then a priority policy) and so lives in core. Discovery is
not: the candidate descriptors come from the injected catalog. Returns the chosen
descriptor; the composition root hands its ``adapter_id`` to the resolver.
"""

from __future__ import annotations

from collections.abc import Sequence

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.common.errors import (
    CapabilityUnavailable,
    UnknownClient,
    UnsupportedExecutionMode,
)


class SelectAdapterForExecutionService:
    """Select the highest-priority adapter for a client, mode and capabilities."""

    def __init__(self, catalog: AdapterCatalogPort) -> None:
        self._catalog = catalog

    def select(
        self,
        client_name: str,
        mode: ExecutionKind,
        required_capabilities: Sequence[ClientCapability] = (),
    ) -> AdapterDescriptor:
        candidates = list(self._catalog.find_by_client_name(client_name))
        if not candidates:
            raise UnknownClient(f"unknown adapter {client_name!r}")

        by_mode = [d for d in candidates if d.supports_mode(mode)]
        if not by_mode:
            raise UnsupportedExecutionMode(
                f"adapter '{client_name}' does not support {mode.value} execution"
            )

        capable = [d for d in by_mode if all(d.has_capability(c) for c in required_capabilities)]
        if not capable:
            missing = ", ".join(c.value for c in required_capabilities)
            raise CapabilityUnavailable(
                f"adapter '{client_name}' lacks required capability: {missing}"
            )

        # Highest priority wins; ties resolve by adapter_id for determinism.
        return max(capable, key=lambda d: (d.priority, d.adapter_id))
