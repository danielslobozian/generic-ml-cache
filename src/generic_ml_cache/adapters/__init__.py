# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client adapters.

Importing this package registers the built-in adapters. The Claude adapter is
registered eagerly. Codex and Cursor are also registered so all three v0.0.1
clients are available out of the box; their flag mappings are best-effort and
documented as such.
"""

from __future__ import annotations

# Eager registration of the built-in adapters.
from . import claude  # noqa: F401  (registers ClaudeAdapter)
from .base import ClientAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter
from .registry import get_adapter, register, registered_names

register(CodexAdapter())
register(CursorAdapter())

__all__ = ["ClientAdapter", "get_adapter", "register", "registered_names"]
