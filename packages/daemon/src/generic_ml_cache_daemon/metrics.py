# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Prometheus metrics setup for the daemon. Requires the optional [metrics] extra."""

from __future__ import annotations

import importlib.util

_PROMETHEUS_INSTALLED = importlib.util.find_spec("prometheus_client") is not None


def is_prometheus_available() -> bool:
    """Return True when the prometheus-client extra is installed."""
    return _PROMETHEUS_INSTALLED
