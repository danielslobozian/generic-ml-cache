# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MetricsPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional


class MetricsPort(ABC):
    """Outbound port for the call journal: append events, query projections.

    Non-load-bearing by contract: record_event must never raise, because
    observability must never break an execution. Implementations swallow
    their own errors at the adapter level.

    Events are the source of truth. hit_counts_by_key, event_counts, and
    last_access are projections over the journal, not stored truths.
    """

    @abstractmethod
    def record_event(
        self,
        event: str,
        *,
        execution_key: Optional[str],
        client: str,
        model: str,
        effort: str,
    ) -> None:
        """Append one journal event. Must never raise."""

    @abstractmethod
    def hit_counts_by_key(self) -> Dict[str, int]:
        """Return {execution_key: hit_count} across all HIT events.

        An empty dict is the correct response when no data is available.
        """

    @abstractmethod
    def event_counts(self) -> Dict[str, int]:
        """Return {event_name: count} across all recorded events.

        An empty dict is the correct response when no data is available.
        """

    @abstractmethod
    def last_access(self) -> Dict[str, float]:
        """Return {execution_key: epoch_seconds} of the latest event per key.

        Used for LRU eviction ordering. An empty dict is the correct response
        when no data is available.
        """
