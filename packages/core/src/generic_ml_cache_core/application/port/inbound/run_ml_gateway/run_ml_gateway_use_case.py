# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlGatewayUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.gateway.gateway_response import GatewayResponse
from generic_ml_cache_core.application.port.inbound.run_ml_gateway.run_ml_gateway_command import (
    RunMlGatewayCommand,
)


class RunMlGatewayUseCase(ABC):
    """Inbound port for the caching gateway proxy.

    The driving adapter (daemon route) depends on this contract and never on
    the implementation. The composition root wires the concrete service in.
    """

    @abstractmethod
    def execute(self, command: RunMlGatewayCommand) -> GatewayResponse:
        """Check the cache and forward to the upstream on a miss."""
