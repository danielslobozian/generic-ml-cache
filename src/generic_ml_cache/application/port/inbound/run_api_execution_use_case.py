# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunApiExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache.application.port.inbound.run_api_execution_command import (
    RunApiExecutionCommand,
)


class RunApiExecutionUseCase(ABC):
    """Inbound port for record-or-replay of a direct ML provider API call."""

    @abstractmethod
    def execute(self, command: RunApiExecutionCommand) -> MlExecution:
        """Resolve the API command and return the resulting execution."""
