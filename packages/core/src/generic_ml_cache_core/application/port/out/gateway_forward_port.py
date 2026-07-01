# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GatewayForwardPort — outbound port for forwarding a request to the upstream API."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from generic_ml_cache_core.application.domain.model.gateway.forwarded_response import (
    ForwardedResponse,
)
from generic_ml_cache_core.application.domain.model.gateway.gateway_request import (
    GatewayRequest,
)


class GatewayForwardPort(ABC):
    """Outbound port for sending a gateway request to a real upstream endpoint.

    The core ring owns this contract. The default implementation
    (``HttpGatewayForwardAdapter``) ships with the library; consumers may
    substitute their own (e.g. a recording stub in tests).
    """

    @abstractmethod
    def forward(
        self,
        gateway_request: GatewayRequest,
        api_token: str,
        target_url: str,
        forward_headers: Mapping[str, str],
    ) -> ForwardedResponse:
        """POST ``gateway_request`` to ``target_url`` and return the raw response."""
