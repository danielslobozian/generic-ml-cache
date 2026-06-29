# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CLI adapter-discovery composition.

The CLI opts into the default catalog/resolver composition (entry-point adapters
merged with in-process registered ones) and exposes the availability/kind helpers
its controllers ask. Discovery itself lives in the adapters package; this module
is the CLI's choice of how to wire it.
"""

from __future__ import annotations

from generic_ml_cache_adapters.discovery.composition import (
    adapter_sources,
    catalog_for,
    default_catalog,
    default_resolver,
    execution_kind_for,
    registered_local_names,
    registered_names,
)
from generic_ml_cache_adapters.discovery.in_memory_adapter_registry import register

__all__ = [
    "register",
    "default_catalog",
    "default_resolver",
    "catalog_for",
    "execution_kind_for",
    "registered_names",
    "registered_local_names",
    "adapter_sources",
]
