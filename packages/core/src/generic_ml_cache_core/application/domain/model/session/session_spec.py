# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionSpec — the optional execution triple attached to a cache session."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSpec:
    """Atomic execution spec for a session: adapter, model, and effort.

    ``client`` and ``model`` are required together; a partial spec (e.g. just a client
    with no model) is invalid and rejected by the CLI before storage. ``effort`` is
    optional and may be an empty string -- the client's own default, or for adapters
    that bake effort into the model name (e.g. Cursor).
    """

    client: str
    model: str
    effort: str
