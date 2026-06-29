# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientCapability — a discrete thing an adapter's client can do."""

from __future__ import annotations

import enum


class ClientCapability(enum.Enum):
    """Capabilities a catalog can advertise and a selection policy can require.

    ``RUN`` — execute a request (every adapter has this). ``LIST_MODELS`` — the
    client can enumerate its models (e.g. ``cursor-agent --list-models`` or an API
    provider's models endpoint); clients without a scriptable listing omit it.
    """

    RUN = "run"
    LIST_MODELS = "list-models"
