# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SystemClock: the real wall-clock implementation of ClockPort."""

from __future__ import annotations

from datetime import datetime, timezone

from generic_ml_cache_core.application.port.out.clock_port import ClockPort


class SystemClock(ClockPort):
    """Reads the operating system clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
