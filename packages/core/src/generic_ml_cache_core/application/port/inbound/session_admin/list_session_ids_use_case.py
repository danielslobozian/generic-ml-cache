# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ListSessionIdsUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ListSessionIdsUseCase(ABC):
    """Inbound port: all known session ids."""

    @abstractmethod
    def list_session_ids(self) -> list[str]: ...
