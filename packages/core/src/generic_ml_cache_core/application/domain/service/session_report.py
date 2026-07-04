# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Session report: a pure projection of a session's journal events + token usage.

``build_session_report`` is deliberately a **pure function** — it takes the session's
journal rows and a ``{execution_key: TokenUsage}`` map (which the caller fetches from the
repository) and returns a :class:`SessionReport`. No ports, no I/O, so it is unit-testable
by asserting numbers, and the CLI renders the result.

Design rulings this encodes (see the usage model):

* **A token is meaningless without its (client/provider, model).** Tokens are aggregated on
  that axis (:class:`ModelUsage`), never summed across models.
* **Unknown is not zero.** An executed call whose execution reported no usage is counted in
  ``unknown_usage``, not folded into the totals as a real zero.
* **No dollars.** ``cost_usd`` is a client-specific advisory estimate; it is not part of the
  report.
* **Sessions span time.** Per-day activity (:class:`DayActivity`) is counts only (model-
  agnostic), so it never mixes tokens across models.
"""

from __future__ import annotations

from collections.abc import Iterable

from generic_ml_cache_core.application.domain.model.session.session_event_row import SessionEventRow
from generic_ml_cache_core.application.domain.model.session.session_report import (
    DayActivity,
    ModelUsage,
    SessionReport,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.common import journal_events

#: Events where a real client call ran (vs. a HIT replay or an offline MISS).
EXECUTED_EVENTS = frozenset(
    {journal_events.RECORD, journal_events.RUN, journal_events.WOULD_HIT, journal_events.WOULD_MISS}
)


def _tokens(usage: TokenUsage | None) -> int | None:
    """Total reported tokens for a usage, or None if the call reported none."""
    if usage is None or (usage.input_tokens is None and usage.output_tokens is None):
        return None
    return (usage.input_tokens or 0) + (usage.output_tokens or 0)


def build_session_report(
    session_id: str,
    events: Iterable[SessionEventRow],
    usage_by_key: dict[str, TokenUsage],
    failed_persistence_count: int = 0,
) -> SessionReport:
    """Aggregate a session's journal rows into a :class:`SessionReport`.

    ``events`` are rows with ``ts`` / ``event`` / ``client`` / ``model`` / ``execution_key``
    (oldest first); ``usage_by_key`` maps an execution key to its :class:`TokenUsage`.
    ``failed_persistence_count`` is how many of the session's runs never finished
    persisting (C-4) — the caller supplies it, since it is a persistence-store fact,
    not derivable from the journal alone.
    """
    models: dict[tuple[str, str], dict[str, int]] = {}
    days: dict[str, dict[str, int]] = {}
    invocations = executions = hits = unknown = 0

    for row in events:
        invocations += 1
        day = (row.ts or "")[:10]
        day_counts = days.setdefault(day, {"invocations": 0, "executions": 0, "hits": 0})
        day_counts["invocations"] += 1
        model_counts = models.setdefault(
            (row.client, row.model),
            {
                "in": 0,
                "out": 0,
                "cache_read": 0,
                "cache_write": 0,
                "reasoning": 0,
                "saved": 0,
                "executions": 0,
                "hits": 0,
            },
        )
        usage = usage_by_key.get(row.execution_key) if row.execution_key else None

        if row.event == journal_events.HIT:
            hits += 1
            day_counts["hits"] += 1
            model_counts["hits"] += 1
            saved = _tokens(usage)
            if saved is not None:
                model_counts["saved"] += saved
        elif row.event in EXECUTED_EVENTS:
            executions += 1
            day_counts["executions"] += 1
            model_counts["executions"] += 1
            if usage is not None and _tokens(usage) is not None:
                model_counts["in"] += usage.input_tokens or 0
                model_counts["out"] += usage.output_tokens or 0
                model_counts["cache_read"] += usage.cache_read_tokens or 0
                model_counts["cache_write"] += usage.cache_write_tokens or 0
                model_counts["reasoning"] += usage.reasoning_tokens or 0
            else:
                unknown += 1

    by_model = [
        ModelUsage(
            client=client,
            model=model,
            spent_input=counts["in"],
            spent_output=counts["out"],
            cache_read_tokens=counts["cache_read"],
            cache_write_tokens=counts["cache_write"],
            reasoning_tokens=counts["reasoning"],
            saved_tokens=counts["saved"],
            executions=counts["executions"],
            hits=counts["hits"],
        )
        for (client, model), counts in sorted(models.items())
    ]
    by_day = [
        DayActivity(
            day=day,
            invocations=counts["invocations"],
            executions=counts["executions"],
            hits=counts["hits"],
        )
        for day, counts in sorted(days.items())
    ]
    return SessionReport(
        session_id=session_id,
        invocations=invocations,
        executions=executions,
        hits=hits,
        unknown_usage=unknown,
        span_start=by_day[0].day if by_day else None,
        span_end=by_day[-1].day if by_day else None,
        by_model=tuple(by_model),
        by_day=tuple(by_day),
        runs_with_failed_persistence=failed_persistence_count,
    )
