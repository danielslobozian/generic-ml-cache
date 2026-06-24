# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Registry mapping provider names to API adapter factories.

Mirrors the client adapter registry pattern: built-in adapters self-register
via the package ``__init__``. Third parties can call :func:`register_api_adapter`
to add their own providers.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.common.errors import UnknownClient

_REGISTRY: Dict[str, Callable[[Optional[str]], ApiClientPort]] = {}


def register_api_adapter(
    name: str, factory: Callable[[Optional[str]], ApiClientPort]
) -> None:
    """Register ``name`` → ``factory(api_key)`` in the API adapter registry."""
    _REGISTRY[name] = factory


def get_api_adapter(name: str, api_key: Optional[str] = None) -> ApiClientPort:
    """Return an adapter instance for ``name``, passing ``api_key`` to the factory.

    When ``api_key`` is ``None`` the adapter reads its key from the environment
    (e.g. ``GEMINI_API_KEY``). Raises :class:`~...errors.UnknownClient` for an
    unregistered provider name.
    """
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise UnknownClient(f"unknown API provider {name!r}; registered: {known}")
    return _REGISTRY[name](api_key)


def registered_api_names() -> List[str]:
    return sorted(_REGISTRY)
