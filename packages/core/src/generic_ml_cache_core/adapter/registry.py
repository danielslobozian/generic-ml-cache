# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Unified adapter registry with automatic discovery.

Adapters are discovered at runtime by scanning the built-in adapter packages
and collecting every class decorated with :func:`adapter`.  Adding a new
adapter to the package is sufficient — no explicit registration list anywhere.

Third-party code and the test suite can inject additional adapters via
:func:`register`.  Registered instances shadow any scanned adapter with the
same name and persist for the lifetime of the process.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, FrozenSet, List, Optional, Type

from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient

_ADAPTER_CLASSES: List[Type[MlRunnerPort]] = []
_EXTRA: Dict[str, MlRunnerPort] = {}

_BUILTIN_PACKAGES = (
    "generic_ml_cache_core.adapter.out.client",
    "generic_ml_cache_core.adapter.out.api",
)


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


def _scan_builtins() -> None:
    """Import every module in the built-in adapter packages.

    This triggers the ``@adapter`` decorator on each adapter class, populating
    ``_ADAPTER_CLASSES``.  Already-imported modules are skipped (Python caches
    imports in ``sys.modules``), so repeated calls are cheap.
    """
    for pkg_name in _BUILTIN_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for info in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{pkg_name}.{info.name}")


def load_adapters(
    whitelist: Optional[FrozenSet[str]] = None,
) -> Dict[str, MlRunnerPort]:
    """Return every available adapter, optionally filtered by *whitelist*.

    Built-in adapters are discovered by scanning the adapter packages and
    collecting ``@adapter``-decorated classes.  They are then merged with
    instances registered via :func:`register`; registered instances take
    precedence over scanned adapters with the same name.

    ``whitelist=None`` returns all discovered adapters.  A non-``None``
    whitelist restricts the result to the named adapters only.
    """
    _scan_builtins()
    result: Dict[str, MlRunnerPort] = {}
    for cls in _ADAPTER_CLASSES:
        name = getattr(cls, "name", None)
        if not name:
            continue
        if whitelist is not None and name not in whitelist:
            continue
        result[name] = cls()
    for name, instance in _EXTRA.items():
        if whitelist is None or name in whitelist:
            result[name] = instance
    return result


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
