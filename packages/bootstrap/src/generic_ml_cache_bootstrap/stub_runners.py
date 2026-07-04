# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Driver-facing hook for the CLI's no-credential stub mode (W28).

When the CLI is invoked without selecting a client, every API client name is
served by the in-process stub adapter — it records/replays a canned response with
no live call, so demos and cache tests exercise the full pipeline without real
credentials. Constructing that concrete stub adapter is the last direct
``cli._compose -> adapters.adapter.outbound`` edge W28 removes; the driver asks the
composition root for the stub-runner map instead.
"""

from __future__ import annotations

from typing import cast

from generic_ml_cache_adapters.adapter.outbound.api.stub_api_client_adapter import (
    StubApiClientAdapter,
)
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)


def stub_api_runners(catalog: AdapterCatalogPort) -> dict[str, RegisteredAdapterPort]:
    """Map every API client name in the catalog to one in-process stub adapter."""
    stub = cast("RegisteredAdapterPort", StubApiClientAdapter())
    return {
        descriptor.client_name: stub
        for descriptor in catalog.list_adapters()
        if descriptor.boundary is AdapterBoundary.API
    }
