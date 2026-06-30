# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EventCountsUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EventCountsUseCase(ABC):
    """Inbound port: {event_name: count} across all recorded journal events."""

    @abstractmethod
    def event_counts(self) -> dict[str, int]: ...
