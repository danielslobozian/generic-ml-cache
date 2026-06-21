# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClockPort contract and the SystemClock adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from generic_ml_cache.adapter.out.clock.system_clock import SystemClock
from generic_ml_cache.application.port.out.clock_port import ClockPort


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ClockPort()  # type: ignore[abstract]


def test_port_requires_now_implementation():
    class MissingNow(ClockPort):
        pass

    with pytest.raises(TypeError):
        MissingNow()  # type: ignore[abstract]


def test_system_clock_is_a_clock_port():
    assert isinstance(SystemClock(), ClockPort)


def test_system_clock_returns_timezone_aware_utc():
    moment = SystemClock().now()
    assert isinstance(moment, datetime)
    assert moment.tzinfo is not None
    assert moment.utcoffset() == timezone.utc.utcoffset(None)


def test_system_clock_is_non_decreasing():
    clock = SystemClock()
    first = clock.now()
    second = clock.now()
    assert second >= first
