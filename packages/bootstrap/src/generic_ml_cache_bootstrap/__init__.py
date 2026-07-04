# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-bootstrap: the composition root and plugin discovery layer.

This is where the application is assembled at startup. It owns two jobs that are
neither pure domain (core) nor a driven adapter (adapters):

* **Discovery** — find the ``gmlcache.adapters`` plugins, whitelist them at load
  time, and decide which distributions are trusted (provenance).
* **Composition** — wire the core use cases to the concrete adapters and hand the
  drivers (CLI, daemon) a ready application API.

It depends on both ``core`` and ``adapters`` (it must ``new`` the infra), and is
imported only by the drivers — never by an adapter (that would be a leaf calling
the composition root). See ``docs/design/bootstrap-split-and-v4-plan.md``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache-bootstrap")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+unknown"
