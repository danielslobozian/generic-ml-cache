# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GetSessionSpecUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_command import (
    GetSessionSpecCommand,
)


class GetSessionSpecUseCase(ABC):
    """Inbound port: the execution spec attached to a session, or None."""

    @abstractmethod
    def get_spec(self, command: GetSessionSpecCommand) -> SessionSpec | None: ...
