# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ValidateExecutionModeService — gate a (client, mode) pair before running.

A composition root (e.g. the daemon ``/run`` route over a whitelisted catalog)
asks core to validate that the requested client can run in the requested mode.
The distinction between "unknown client" and "client present but wrong mode" is
application logic; the available universe is the injected catalog.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.common.errors import UnknownClient, UnsupportedExecutionMode


class ValidateExecutionModeService:
    """Raise a clear error if a client cannot run in the requested mode."""

    def __init__(self, catalog: AdapterCatalogPort) -> None:
        self._catalog = catalog

    def validate(self, client_name: str, mode: ExecutionKind) -> None:
        if self._catalog.supports(client_name, mode):
            return
        if not self._catalog.find_by_client_name(client_name):
            raise UnknownClient(f"unknown adapter {client_name!r}")
        raise UnsupportedExecutionMode(
            f"adapter '{client_name}' does not support {mode.value} execution"
        )
