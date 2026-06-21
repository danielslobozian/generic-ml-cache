# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunManagedLocalExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)


class RunManagedLocalExecutionUseCase(ABC):
    """Inbound port for record-or-replay of a fully managed local client call.

    The driving adapter (CLI, daemon, library consumer) depends on this contract
    and never on the implementation. The composition root wires the concrete
    service in.
    """

    @abstractmethod
    def execute(self, command: RunManagedLocalExecutionCommand) -> MlExecution:
        """Resolve the command and return the resulting execution."""
