# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Prometheus metrics setup for the daemon. Requires the optional [metrics] extra."""

from __future__ import annotations

try:
    import prometheus_client  # type: ignore[import-untyped]  # noqa: F401

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False


def is_prometheus_available() -> bool:
    """Return True when the prometheus-client extra is installed."""
    return _AVAILABLE
