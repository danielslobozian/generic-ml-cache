# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)


class RunMlExecutionUseCase(ABC):
    """Inbound port for record-or-replay of any ML execution.

    The driving adapter (CLI, daemon, library consumer) depends on this contract
    and never on the implementation. The composition root wires the concrete
    service in.
    """

    @abstractmethod
    def execute(self, command: RunMlExecutionCommand) -> MlExecution:
        """Resolve the command and return the resulting execution."""
