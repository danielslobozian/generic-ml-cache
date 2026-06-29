# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client adapters.

Built-in adapters carry the ``@adapter`` decorator and are discovered
automatically by the unified registry scanner.  No explicit registration here.
"""

from __future__ import annotations

from generic_ml_cache_core.adapter.registry import get_adapter, register, registered_names

from generic_ml_cache_adapters.adapter.out.client.cli_runtime import CliRuntime, wire_cli_client

__all__ = ["CliRuntime", "wire_cli_client", "get_adapter", "register", "registered_names"]
