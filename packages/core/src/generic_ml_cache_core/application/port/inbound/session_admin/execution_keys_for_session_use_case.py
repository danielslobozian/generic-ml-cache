# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionKeysForSessionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_command import (
    ExecutionKeysForSessionCommand,
)


class ExecutionKeysForSessionUseCase(ABC):
    """Inbound port: the execution keys recorded under a session."""

    @abstractmethod
    def execution_keys_for_session(self, command: ExecutionKeysForSessionCommand) -> list[str]: ...
