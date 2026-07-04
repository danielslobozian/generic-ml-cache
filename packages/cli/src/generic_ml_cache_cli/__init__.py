# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-cli: the terminal UI over generic-ml-cache-core.

A thin inbound driver: it reads configuration (an INI file), provides the data
source (store location), and maps the ``gmlcache`` terminal commands onto the
core library's public APIs. The engine logic lives in generic-ml-cache-core; the
concrete adapters are assembled by generic-ml-cache-bootstrap (the composition
root). This package depends on core and bootstrap only — never on the adapters
package directly (W28 driver isolation).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache-cli")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"

from generic_ml_cache_core.common.errors import UnknownClient  # noqa: E402

from generic_ml_cache_cli._compose import (
    build_use_cases,  # noqa: E402  # public embedding entry point
)
from generic_ml_cache_cli.discovery import register  # noqa: E402  # adapter registration seam

__all__ = ["__version__", "register", "UnknownClient", "build_use_cases"]
