# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ListSessionTagsUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_command import (
    ListSessionTagsCommand,
)


class ListSessionTagsUseCase(ABC):
    """Inbound port: list a session's tags."""

    @abstractmethod
    def list_tags(self, command: ListSessionTagsCommand) -> list[str]: ...
