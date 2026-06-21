# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunPassthroughExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.run_passthrough_execution_command import (
    RunPassthroughExecutionCommand,
)


class RunPassthroughExecutionUseCase(ABC):
    """Inbound port for record-or-replay of a passthrough (alias) client call."""

    @abstractmethod
    def execute(self, command: RunPassthroughExecutionCommand) -> MlExecution:
        """Resolve the passthrough command and return the resulting execution."""
