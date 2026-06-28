# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-adapters: concrete outbound port implementations.

This package provides the infrastructure layer for generic-ml-cache-core:
SQLite persistence, filesystem blob storage, AES-GCM encryption, ML client
runners (claude, codex, cursor-agent), REST API adapters (anthropic, openai,
gemini), metrics, clock, and HTTP gateway forwarding.

ML client adapters are declared via the ``gmlcache.adapters`` entry-point group
and are discovered automatically by the core registry when this package is
installed.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache-adapters")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+unknown"
