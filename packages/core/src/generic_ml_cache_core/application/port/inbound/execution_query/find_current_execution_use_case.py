# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FindCurrentExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)


class FindCurrentExecutionUseCase(ABC):
    """Inbound port: the current cached execution for a key, or None."""

    @abstractmethod
    def find_current(self, command: FindCurrentExecutionCommand) -> MlExecution | None: ...
