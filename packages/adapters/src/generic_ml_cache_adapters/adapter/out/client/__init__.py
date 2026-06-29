# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client adapters.

Built-in adapters declare themselves via the ``gmlcache.adapters`` entry-point
group and a ``descriptor()`` classmethod; the discovery layer (catalogs and
resolvers) finds and constructs them.
"""

from __future__ import annotations

from generic_ml_cache_adapters.adapter.out.client.cli_runtime import CliRuntime, wire_cli_client

__all__ = ["CliRuntime", "wire_cli_client"]
