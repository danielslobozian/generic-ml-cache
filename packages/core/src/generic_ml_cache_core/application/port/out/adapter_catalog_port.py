# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterCatalogPort — the universe of adapters available to this execution.

Core asks the catalog availability/capability questions ("is claude available?",
"which adapters support managed-local?"). It does NOT discover them: the catalog
is built and injected by the composition root (CLI/daemon/tests), which decides
the discovery mechanism (entry-point scan, a whitelist filter, a static list).
Core sees only the adapter universe it was given.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind


@runtime_checkable
class AdapterCatalogPort(Protocol):
    """Read-only view of the adapters available to this execution."""

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        """Every adapter in this catalog (already filtered by composition policy)."""
        ...

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        """Descriptors whose ``client_name`` matches (empty if the client is absent)."""
        ...

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        """True if some adapter for ``client_name`` supports the given execution mode."""
        ...
