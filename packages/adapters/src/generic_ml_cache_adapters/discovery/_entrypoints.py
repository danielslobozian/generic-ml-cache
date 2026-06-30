# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Low-level entry-point access for the discovery layer.

This is the one place that touches ``importlib.metadata`` — the packaging system.
It belongs in the adapters/infrastructure package, never in core.
"""

from __future__ import annotations

import importlib.metadata

ADAPTER_ENTRYPOINT_GROUP = "gmlcache.adapters"
ADAPTER_CONTRACT_VERSION = "1"


def iter_entry_points(group: str = ADAPTER_ENTRYPOINT_GROUP) -> list:
    """Return the entry points in ``group`` (Python 3.9-safe)."""
    return list(importlib.metadata.entry_points(group=group))
    return list(importlib.metadata.entry_points().get(group, []))  # type: ignore[union-attr]


def describe_source(ep: object) -> str:
    """Human-readable "<package> <version>" for the distribution providing ``ep``."""
    dist = getattr(ep, "dist", None)
    if dist is None:
        return getattr(ep, "value", str(ep))
    name = dist.metadata.get("Name", "") or ""
    version = dist.metadata.get("Version", "") or ""
    if name and version:
        return f"{name} {version}"
    return name or getattr(ep, "value", str(ep))
