# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Lock-in: core never discovers adapters by scanning Python packaging metadata.

Adapter discovery is infrastructure — it lives in the adapters package behind
AdapterCatalogPort and is injected by the composition root. This guard fails if
any core source file reintroduces entry-point scanning, or if core regrows a
global ``register`` / ``get_adapter`` plugin API. (import-linter can't target a
single external submodule like ``importlib.metadata``, so this is a unit guard.)
"""

from __future__ import annotations

from pathlib import Path

import generic_ml_cache_core

_CORE_SRC = Path(generic_ml_cache_core.__file__).parent


def _core_python_files():
    return [p for p in _CORE_SRC.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_entry_point_scanning_in_core():
    offenders = []
    for path in _core_python_files():
        text = path.read_text(encoding="utf-8")
        # The package may read its OWN version via importlib.metadata.version; that
        # is not discovery. Scanning the adapter entry-point group is.
        if "entry_points(" in text or "gmlcache.adapters" in text:
            offenders.append(path.relative_to(_CORE_SRC).as_posix())
    assert offenders == [], f"core must not scan adapter entry points: {offenders}"


def test_core_exposes_no_global_adapter_registry():
    # The plugin registry moved to the adapters package; core only defines ports.
    assert not hasattr(generic_ml_cache_core, "register")
    assert not hasattr(generic_ml_cache_core, "get_adapter")
