# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""UntagSessionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_command import (
    UntagSessionCommand,
)


class UntagSessionUseCase(ABC):
    """Inbound port: detach a tag from a session."""

    @abstractmethod
    def untag(self, command: UntagSessionCommand) -> None: ...
