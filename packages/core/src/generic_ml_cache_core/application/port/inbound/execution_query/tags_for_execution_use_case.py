# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TagsForExecutionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_command import (
    TagsForExecutionCommand,
)


class TagsForExecutionUseCase(ABC):
    """Inbound port: the sorted tags on a current execution."""

    @abstractmethod
    def tags_for(self, command: TagsForExecutionCommand) -> list[str]: ...
