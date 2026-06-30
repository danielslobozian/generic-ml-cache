# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionQueryService — the execution-query capability (read stored executions).

One application service implementing the capability's read use cases, each a
distinct method backed by its own inbound-port ABC, delegating to the execution
repository out-port.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_use_case import (
    FindCurrentExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_command import (
    FindExecutionsByKeyPrefixCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_use_case import (
    FindExecutionsByKeyPrefixUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.list_execution_summaries_use_case import (
    ListExecutionSummariesUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_command import (
    TagsForExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_use_case import (
    TagsForExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.total_stored_bytes_use_case import (
    TotalStoredBytesUseCase,
)
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
    ExecutionSummary,
)


class ExecutionQueryService(
    ListExecutionSummariesUseCase,
    TotalStoredBytesUseCase,
    TagsForExecutionUseCase,
    FindCurrentExecutionUseCase,
    FindExecutionsByKeyPrefixUseCase,
):
    """Read the stored executions via the execution repository out-port."""

    def __init__(self, repository: ExecutionRepositoryPort) -> None:
        self._repository = repository

    def list_summaries(self) -> list[ExecutionSummary]:
        return self._repository.current_execution_summaries()

    def total_stored_bytes(self) -> int:
        return self._repository.total_stored_bytes()

    def tags_for(self, command: TagsForExecutionCommand) -> list[str]:
        return self._repository.tags_for(command.execution_key)

    def find_current(self, command: FindCurrentExecutionCommand) -> MlExecution | None:
        return self._repository.find_current(command.execution_key)

    def find_by_key_prefix(self, command: FindExecutionsByKeyPrefixCommand) -> list[MlExecution]:
        return self._repository.find_current_by_key_prefix(command.key_prefix)
