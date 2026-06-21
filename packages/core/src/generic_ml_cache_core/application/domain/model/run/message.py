# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Message."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    """One message in an API call's context: a role and its content.

    Provider-agnostic — the caller builds the full message list and gmlcache
    forwards it to the provider. ``role`` is kept as a plain string because
    providers differ on the roles they accept (system, user, assistant, tool, …).
    """

    role: str
    content: str
