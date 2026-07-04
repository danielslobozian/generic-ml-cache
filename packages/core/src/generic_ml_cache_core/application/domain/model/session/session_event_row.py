# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionEventRow."""

from __future__ import annotations

from typing import NamedTuple


class SessionEventRow(NamedTuple):
    """One journal event in a session, with the fields a session report needs:
    the ISO timestamp (for per-day grouping), the event name, the client/provider
    and model (the token axis), and the execution key (to look up token usage).

    A domain row, not a port concept: it is the shape the session-report projection
    reads. The MetricsPort merely returns it — hence it lives in the domain model
    and the port imports it (a port referencing a domain model, never the reverse).
    """

    ts: str
    event: str
    client: str
    model: str
    execution_key: str | None
