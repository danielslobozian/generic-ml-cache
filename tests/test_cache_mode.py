# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for CacheMode."""

from __future__ import annotations

from generic_ml_cache.application.domain.model.run.cache_mode import CacheMode


def test_cache_value():
    assert CacheMode.CACHE.value == "cache"


def test_offline_value():
    assert CacheMode.OFFLINE.value == "offline"


def test_refresh_value():
    assert CacheMode.REFRESH.value == "refresh"


def test_string_roundtrip():
    for cache_mode in CacheMode:
        assert CacheMode(cache_mode.value) is cache_mode


def test_exactly_three_modes():
    assert len(CacheMode) == 3
