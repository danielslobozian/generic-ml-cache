# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ListExecutionSummariesUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.out.execution_repository_port import ExecutionSummary


class ListExecutionSummariesUseCase(ABC):
    """Inbound port: the uniform reporting view of the current executions."""

    @abstractmethod
    def list_summaries(self) -> list[ExecutionSummary]: ...
