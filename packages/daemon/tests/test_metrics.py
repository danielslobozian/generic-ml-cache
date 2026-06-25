# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Prometheus metrics helpers."""

from __future__ import annotations

from generic_ml_cache_daemon.metrics import is_prometheus_available


def test_is_prometheus_available_returns_bool() -> None:
    result = is_prometheus_available()
    assert isinstance(result, bool)


def test_is_prometheus_available_true_when_installed() -> None:
    # prometheus-client is in the [dev] extra, so it is always installed
    # when running the test suite.
    assert is_prometheus_available() is True
