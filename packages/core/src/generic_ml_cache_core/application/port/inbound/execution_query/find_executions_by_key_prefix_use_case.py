# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FindExecutionsByKeyPrefixUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_command import (
    FindExecutionsByKeyPrefixCommand,
)


class FindExecutionsByKeyPrefixUseCase(ABC):
    """Inbound port: current executions whose key starts with a prefix."""

    @abstractmethod
    def find_by_key_prefix(
        self, command: FindExecutionsByKeyPrefixCommand
    ) -> list[MlExecution]: ...
