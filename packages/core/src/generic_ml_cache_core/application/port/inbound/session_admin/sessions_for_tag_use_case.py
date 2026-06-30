# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionsForTagUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_command import (
    SessionsForTagCommand,
)


class SessionsForTagUseCase(ABC):
    """Inbound port: the session ids carrying a tag."""

    @abstractmethod
    def sessions_for_tag(self, command: SessionsForTagCommand) -> list[str]: ...
