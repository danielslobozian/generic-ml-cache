# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CheckClientAvailabilityService — "is this client available?".

The required feature ("the application must know whether claude/codex/cursor is
available") expressed as core application logic over an injected catalog. Core
asks the question; it never discovers adapters itself.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.catalog.client_availability import (
    ClientAvailability,
)
from generic_ml_cache_core.application.port.out.adapter_catalog_port import AdapterCatalogPort


class CheckClientAvailabilityService:
    """Report whether a client is available, and which adapters serve it."""

    def __init__(self, catalog: AdapterCatalogPort) -> None:
        self._catalog = catalog

    def check(self, client_name: str) -> ClientAvailability:
        candidates = tuple(self._catalog.find_by_client_name(client_name))
        return ClientAvailability(
            client_name=client_name,
            available=bool(candidates),
            candidates=candidates,
        )
