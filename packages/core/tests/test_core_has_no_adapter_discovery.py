# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Lock-in: core stays a pure library — no adapter discovery, no raw I/O.

Adapter discovery is infrastructure — it lives in the adapters package behind
AdapterCatalogPort and is injected by the composition root. This guard fails if
any core source file reintroduces entry-point scanning, regrows a global
``register`` / ``get_adapter`` plugin API, or performs raw filesystem / subprocess
/ socket I/O (every side effect belongs behind a port). These are unit guards
because import-linter can't target a single external submodule like
``importlib.metadata``, and — as the ``core.stream`` leak showed — can't see an
infrastructure class that lives *outside* ``application/`` and imports nothing
forbidden, yet still does I/O in the pure core.
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


# Raw I/O call signatures a pure core must never contain — side effects go through
# a port (BlobStorePort, DiagnosticsPort, WorkspacePort, ...) implemented in the
# adapters package. These are call/import forms, not bare words, so prose that
# merely mentions "subprocess" or "filesystem" does not trip the guard.
_IO_SIGNATURES = (
    "open(",
    ".mkdir(",
    ".write_text(",
    ".write_bytes(",
    ".read_text(",
    ".read_bytes(",
    "import socket",
    "socket.socket(",
    "import subprocess",
    "subprocess.run(",
    "subprocess.Popen(",
    "urllib.request",
)


def test_no_raw_io_in_core():
    """Core performs no filesystem, subprocess, or socket I/O. This is the guard the
    ``core.stream.StreamWriter`` leak slipped past — it lived outside ``application/``
    (so no import-linter contract watched it) yet opened files in the pure core."""
    offenders = []
    for path in _core_python_files():
        text = path.read_text(encoding="utf-8")
        for sig in _IO_SIGNATURES:
            if sig in text:
                offenders.append(f"{path.relative_to(_CORE_SRC).as_posix()}: {sig!r}")
    assert offenders == [], f"core must not perform raw I/O: {offenders}"
