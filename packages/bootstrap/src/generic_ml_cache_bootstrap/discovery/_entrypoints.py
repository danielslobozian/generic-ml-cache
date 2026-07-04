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


def iter_entry_points(
    group: str = ADAPTER_ENTRYPOINT_GROUP,
) -> list[importlib.metadata.EntryPoint]:
    """Return the entry points in ``group``."""
    return list(importlib.metadata.entry_points(group=group))


def distribution_name(entry_point: importlib.metadata.EntryPoint) -> str:
    """The name of the distribution providing ``entry_point`` (``""`` if unknown).

    Used to decide trust at load time: an entry point whose distribution is in
    the trusted set is loaded; others are third-party, off unless whitelisted.
    """
    dist = entry_point.dist
    if dist is None or not dist.metadata:
        return ""
    return dist.name or ""


def describe_source(entry_point: importlib.metadata.EntryPoint) -> str:
    """Human-readable "<package> <version>" for the distribution providing ``entry_point``."""
    dist = entry_point.dist
    if dist is None:
        return entry_point.value
    name = dist.name or ""
    version = dist.version or ""
    if name and version:
        return f"{name} {version}"
    return name or entry_point.value
