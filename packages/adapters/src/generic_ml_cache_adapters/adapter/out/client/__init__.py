# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client adapters.

Built-in adapters carry the ``@adapter`` decorator and are discovered
automatically by the unified registry scanner.  No explicit registration here.
"""

from __future__ import annotations

from generic_ml_cache_core.adapter.registry import get_adapter, register, registered_names
from generic_ml_cache_core.application.port.out.base import ClientAdapter

__all__ = ["ClientAdapter", "get_adapter", "register", "registered_names"]
