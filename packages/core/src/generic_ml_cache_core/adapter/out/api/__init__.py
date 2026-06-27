# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""API adapters.

Built-in adapters carry the ``@adapter`` decorator and are discovered
automatically by the unified registry scanner.  No explicit registration here.
"""

from __future__ import annotations

from generic_ml_cache_core.adapter.registry import get_adapter, register, registered_names

__all__ = ["get_adapter", "register", "registered_names"]
