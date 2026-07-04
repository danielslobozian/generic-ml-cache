# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterDescriptor — core's metadata view of one available adapter.

A descriptor answers "what is this adapter?" without instantiating it: its stable
id, the client it serves, where it lives (boundary), which execution modes and
capabilities it offers. The catalog returns descriptors so availability and
selection stay lightweight; the resolver turns a chosen id into a real adapter.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

# Which execution modes each boundary supports — a domain rule about the
# boundary, so it lives with the value object that owns the fields (G2).
_LOCAL_CLI_MODES = frozenset({ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH})
_API_MODES = frozenset({ExecutionKind.API})


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
    supported_modes: frozenset[ExecutionKind]
    capabilities: frozenset[ClientCapability] = field(default_factory=frozenset[ClientCapability])
    display_name: str = ""
    priority: int = 0

    @classmethod
    def local_cli(
        cls,
        client_name: str,
        capabilities: Iterable[ClientCapability],
        display_name: str,
        priority: int = 0,
    ) -> AdapterDescriptor:
        """A local CLI client: managed-local + passthrough, id ``"<client>.cli"``."""
        return cls(
            adapter_id=f"{client_name}.cli",
            client_name=client_name,
            boundary=AdapterBoundary.LOCAL_CLI,
            supported_modes=_LOCAL_CLI_MODES,
            capabilities=frozenset(capabilities),
            display_name=display_name,
            priority=priority,
        )

    @classmethod
    def api(
        cls,
        client_name: str,
        capabilities: Iterable[ClientCapability],
        display_name: str,
        priority: int = 0,
    ) -> AdapterDescriptor:
        """A REST API provider: API mode only, id ``"<client>.api"``."""
        return cls(
            adapter_id=f"{client_name}.api",
            client_name=client_name,
            boundary=AdapterBoundary.API,
            supported_modes=_API_MODES,
            capabilities=frozenset(capabilities),
            display_name=display_name,
            priority=priority,
        )

    def supports_mode(self, mode: ExecutionKind) -> bool:
        return mode in self.supported_modes

    def has_capability(self, capability: ClientCapability) -> bool:
        return capability in self.capabilities
