# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Helpers for building AdapterDescriptors from an adapter's own metadata.

Each adapter declares its descriptor via a tiny ``descriptor()`` classmethod that
calls one of these; the catalog reads those descriptors without instantiating the
adapter. Boundary and supported-mode conventions live here so the adapters stay
declarative (id, capabilities, display name).
"""

from __future__ import annotations

from collections.abc import Iterable

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

_LOCAL_CLI_MODES = frozenset({ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH})
_API_MODES = frozenset({ExecutionKind.API})


def local_cli_descriptor(
    client_name: str,
    capabilities: Iterable[ClientCapability],
    display_name: str,
    priority: int = 0,
) -> AdapterDescriptor:
    """A local CLI client: managed-local + passthrough, id ``"<client>.cli"``."""
    return AdapterDescriptor(
        adapter_id=f"{client_name}.cli",
        client_name=client_name,
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=_LOCAL_CLI_MODES,
        capabilities=frozenset(capabilities),
        display_name=display_name,
        priority=priority,
    )


def api_descriptor(
    client_name: str,
    capabilities: Iterable[ClientCapability],
    display_name: str,
    priority: int = 0,
) -> AdapterDescriptor:
    """A REST API provider: API mode only, id ``"<client>.api"``."""
    return AdapterDescriptor(
        adapter_id=f"{client_name}.api",
        client_name=client_name,
        boundary=AdapterBoundary.API,
        supported_modes=_API_MODES,
        capabilities=frozenset(capabilities),
        display_name=display_name,
        priority=priority,
    )
