# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClockPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ClockPort(ABC):
    """Outbound port for reading the current time.

    Time is ambient I/O, so the core never calls ``datetime.now()`` directly —
    it reads the clock through this port. The composition root injects a real
    clock; a test injects a fixed one. This keeps the engine deterministic and
    free of hidden wall-clock dependencies.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
