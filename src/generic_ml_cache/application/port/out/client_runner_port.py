# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientRunnerPort."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.execution_output import ExecutionOutput


class ClientRunnerPort(ABC):
    """Outbound port for launching a local ML client and capturing its output.

    The adapter is the only place that knows a specific client's CLI flags,
    isolation mechanism, and output format. The core names only this contract.
    """

    @abstractmethod
    def run(self, client_run_request: ClientRunRequest) -> ExecutionOutput:
        """Launch the client described by ``client_run_request`` and return its
        captured output. Raises on unrecoverable launch failure."""
