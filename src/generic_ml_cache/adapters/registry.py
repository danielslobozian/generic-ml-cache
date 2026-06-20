# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Registry mapping client names to adapters.

Built-in adapters self-register on import. Third parties (and the test-suite)
can register their own adapters via :func:`register` -- that is how a fake
client is plugged in without shipping it in the package.
"""

from __future__ import annotations

from typing import Dict

from ..common.errors import UnknownClient
from .base import ClientAdapter

_REGISTRY: Dict[str, ClientAdapter] = {}


def register(adapter: ClientAdapter) -> ClientAdapter:
    _REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(name: str) -> ClientAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise UnknownClient(f"unknown client {name!r}; registered: {known}")


def registered_names() -> list[str]:
    return sorted(_REGISTRY)
