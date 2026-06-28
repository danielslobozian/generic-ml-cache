# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Unified adapter registry with automatic discovery.

Adapters declare themselves via the ``gmlcache.adapters`` entry-point group.
Installing ``generic-ml-cache-adapters`` (or any third-party adapter package)
registers its adapters without any change to core.  The whitelist applies
uniformly to all adapters.

Third-party code and the test suite can also inject additional adapters via
:func:`register`.  Registered instances shadow any entry-point adapter with
the same name.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
import warnings
from typing import Dict, FrozenSet, List, Optional, Type

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient

ADAPTER_CONTRACT_VERSION = "1"
"""The adapter contract generation this core version implements.

Third-party adapters may declare ``adapter_contract_version = "1"`` as a class
attribute to assert they target this contract generation.  A mismatch causes
the loader to skip the adapter and emit a :mod:`warnings` warning.  Absence of
the attribute is treated as compatible (no assertion).
"""

_ENTRYPOINT_GROUP = "gmlcache.adapters"

_ADAPTER_CLASSES: List[Type[MlRunnerPort]] = []
_EXTRA: Dict[str, MlRunnerPort] = {}
_ENTRYPOINTS_LOADED: bool = False
_ENTRYPOINT_INSTANCES: Dict[str, MlRunnerPort] = {}
_ENTRYPOINT_SOURCES: Dict[str, str] = {}


def adapter(cls: Type[MlRunnerPort]) -> Type[MlRunnerPort]:
    """Class decorator that marks an adapter class for automatic discovery.

    Equivalent to Spring's ``@Component``: annotate the class once and the
    registry scanner finds it at runtime — no centralized list to maintain.
    """
    if cls not in _ADAPTER_CLASSES:
        _ADAPTER_CLASSES.append(cls)
    return cls


def register(instance: MlRunnerPort) -> None:
    """Register a pre-built *instance* under its own name.

    Intended for tests and third-party code that cannot use the :func:`adapter`
    class decorator (e.g. adapters defined outside the built-in packages).
    Registered instances shadow any scanned adapter with the same name.
    """
    _EXTRA[instance.name] = instance


def _entry_points_for_group() -> list:
    """Return entry points for the gmlcache.adapters group, Python 3.9-safe."""
    if sys.version_info >= (3, 10):
        return list(importlib.metadata.entry_points(group=_ENTRYPOINT_GROUP))
    return list(importlib.metadata.entry_points().get(_ENTRYPOINT_GROUP, []))  # type: ignore[union-attr]


def _describe_ep_source(ep: object) -> str:
    """Return a human-readable source description for an entry-point object."""
    dist = getattr(ep, "dist", None)
    if dist is None:
        return getattr(ep, "value", str(ep))
    pkg_name: str = dist.metadata.get("Name", "") or ""
    pkg_version: str = dist.metadata.get("Version", "") or ""
    if pkg_name and pkg_version:
        return f"{pkg_name} {pkg_version}"
    return pkg_name or getattr(ep, "value", str(ep))


def _load_entry_points() -> None:
    """Discover and instantiate adapters from the ``gmlcache.adapters`` entry point group.

    Each adapter class is inspected for an optional ``adapter_contract_version``
    attribute.  If present and incompatible with :data:`ADAPTER_CONTRACT_VERSION`,
    the adapter is skipped with a :mod:`warnings` warning.  Any load or
    instantiation failure is also warned and skipped — broken third-party code
    must never crash core.

    Results are cached in :data:`_ENTRYPOINT_INSTANCES`; subsequent calls are
    no-ops.
    """
    global _ENTRYPOINTS_LOADED
    if _ENTRYPOINTS_LOADED:
        return
    _ENTRYPOINTS_LOADED = True

    for ep in _entry_points_for_group():
        ep_key: str = getattr(ep, "name", str(ep))
        try:
            cls = ep.load()
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"gmlcache: could not load entry-point adapter {ep_key!r}: {exc}",
                stacklevel=2,
            )
            continue

        declared_version = getattr(cls, "adapter_contract_version", None)
        if declared_version is not None and declared_version != ADAPTER_CONTRACT_VERSION:
            warnings.warn(
                f"gmlcache: entry-point adapter {ep_key!r} declares contract version "
                f"{declared_version!r} but this core requires {ADAPTER_CONTRACT_VERSION!r}; "
                "skipping",
                stacklevel=2,
            )
            continue

        adapter_name: Optional[str] = getattr(cls, "name", None)
        if not adapter_name:
            warnings.warn(
                f"gmlcache: entry-point adapter {ep_key!r} has no 'name' class attribute; skipping",
                stacklevel=2,
            )
            continue

        try:
            instance: MlRunnerPort = cls()
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"gmlcache: could not instantiate entry-point adapter {ep_key!r}: {exc}",
                stacklevel=2,
            )
            continue

        _ENTRYPOINT_INSTANCES[adapter_name] = instance
        _ENTRYPOINT_SOURCES[adapter_name] = _describe_ep_source(ep)


def load_adapters(
    whitelist: Optional[FrozenSet[str]] = None,
) -> Dict[str, MlRunnerPort]:
    """Return every available adapter, optionally filtered by *whitelist*.

    Discovery order (later entries win on name collision):
    1. Entry-point adapters from the ``gmlcache.adapters`` group.
    2. Instances injected via :func:`register` (tests / programmatic use).

    ``whitelist=None`` returns all discovered adapters.  A non-``None``
    whitelist restricts the result to the named adapters only.
    """
    _load_entry_points()
    result: Dict[str, MlRunnerPort] = {}
    for name, instance in _ENTRYPOINT_INSTANCES.items():
        if whitelist is None or name in whitelist:
            result[name] = instance
    for name, instance in _EXTRA.items():
        if whitelist is None or name in whitelist:
            result[name] = instance
    return result


def adapter_sources(
    whitelist: Optional[FrozenSet[str]] = None,
) -> Dict[str, str]:
    """Return a mapping of entry-point adapter name → source package description.

    Only entry-point adapters are included.  Built-in adapters and
    programmatically registered adapters (tests, embedding apps) are omitted.
    The result is empty when no third-party adapter packages are installed.

    Intended for ``gmlcache doctor`` to show which packages contributed adapters.
    """
    load_adapters(whitelist)
    if whitelist is None:
        return dict(_ENTRYPOINT_SOURCES)
    return {name: src for name, src in _ENTRYPOINT_SOURCES.items() if name in whitelist}


def get_adapter(
    name: str,
    whitelist: Optional[FrozenSet[str]] = None,
) -> MlRunnerPort:
    """Return the adapter for *name* or raise :class:`~...UnknownClient`."""
    registry = load_adapters(whitelist)
    try:
        return registry[name]
    except KeyError:
        known = ", ".join(sorted(registry)) or "(none)"
        raise UnknownClient(f"unknown adapter {name!r}; available: {known}")


def registered_names(whitelist: Optional[FrozenSet[str]] = None) -> list[str]:
    """Return a sorted list of all available adapter names."""
    return sorted(load_adapters(whitelist))


def registered_local_names(whitelist: Optional[FrozenSet[str]] = None) -> list[str]:
    """Return a sorted list of LOCAL_MANAGED adapter names only.

    Useful for commands that wrap a native binary (``alias``, ``check``) where
    API adapters are not applicable.
    """
    from generic_ml_cache_core.application.domain.model.execution.execution_kind import (
        ExecutionKind,
    )

    return sorted(
        name
        for name, a in load_adapters(whitelist).items()
        if getattr(a, "execution_kind", None) is ExecutionKind.LOCAL_MANAGED
    )


def resolve_execution_kind(
    client: str, whitelist: Optional[FrozenSet[str]] = None
) -> ExecutionKind:
    """Return the execution kind for *client* via the unified adapter registry."""
    return get_adapter(client, whitelist=whitelist).execution_kind
