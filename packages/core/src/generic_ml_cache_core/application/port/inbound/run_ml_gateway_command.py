# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlGatewayCommand — the inbound command for a caching gateway call."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from generic_ml_cache_core.application.domain.model.gateway.gateway_request import (
    GatewayRequest,
)


@dataclass(frozen=True)
class RunMlGatewayCommand:
    """Input to the gateway use case.

    Carries the parsed request body, the caller's API token, the upstream URL
    to forward to on a cache miss, and an optional session identifier for
    grouping calls in the execution store.
    """

    gateway_request: GatewayRequest
    api_token: str
    target_url: str
    session_id: str | None = None
    forward_headers: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "forward_headers", MappingProxyType(dict(self.forward_headers)))
