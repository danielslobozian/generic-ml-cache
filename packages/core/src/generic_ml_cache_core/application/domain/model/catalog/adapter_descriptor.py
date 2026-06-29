# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterDescriptor — core's metadata view of one available adapter.

A descriptor answers "what is this adapter?" without instantiating it: its stable
id, the client it serves, where it lives (boundary), which execution modes and
capabilities it offers. The catalog returns descriptors so availability and
selection stay lightweight; the resolver turns a chosen id into a real adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind


@dataclass(frozen=True)
class AdapterDescriptor:
    """Immutable metadata describing one adapter in the catalog.

    ``adapter_id`` is the stable selection key (e.g. ``"claude.cli"``,
    ``"anthropic.api"``) — unique even when several adapters share a client name.
    ``client_name`` is what a user types (e.g. ``"claude"``). ``priority`` orders
    candidates when more than one serves the same client/mode (higher wins).
    """

    adapter_id: str
    client_name: str
    boundary: AdapterBoundary
    supported_modes: FrozenSet[ExecutionKind]
    capabilities: FrozenSet[ClientCapability] = field(default_factory=frozenset)
    display_name: str = ""
    priority: int = 0

    def supports_mode(self, mode: ExecutionKind) -> bool:
        return mode in self.supported_modes

    def has_capability(self, capability: ClientCapability) -> bool:
        return capability in self.capabilities
