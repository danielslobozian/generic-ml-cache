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
from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.out.metrics_port import SessionEventRow

#: Events where a real client call ran (vs. a HIT replay or an offline MISS).
EXECUTED_EVENTS = frozenset({"record", "run", "would_hit", "would_miss"})
_HIT = "hit"


@dataclass(frozen=True)
class ModelUsage:
    """Token usage for one (client/provider, model) within a session."""

    client: str
    model: str
    spent_input: int
    spent_output: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    saved_tokens: int
    executions: int
    hits: int

    @property
    def spent_tokens(self) -> int:
        return self.spent_input + self.spent_output


@dataclass(frozen=True)
class DayActivity:
    """Activity counts for one day of a session (model-agnostic, no tokens)."""

    day: str
    invocations: int
    executions: int
    hits: int


@dataclass(frozen=True)
class SessionReport:
    """The roll-up for one session: headline counts, per-model token usage, per-day activity."""

    session_id: str
    invocations: int
    executions: int
    hits: int
    unknown_usage: int
    span_start: str | None
    span_end: str | None
    by_model: list[ModelUsage]
    by_day: list[DayActivity]

    @property
    def day_count(self) -> int:
        return len(self.by_day)


def _tokens(usage: TokenUsage | None) -> int | None:
    """Total reported tokens for a usage, or None if the call reported none."""
    if usage is None or (usage.input_tokens is None and usage.output_tokens is None):
        return None
    return (usage.input_tokens or 0) + (usage.output_tokens or 0)


def build_session_report(
    session_id: str,
    events: Iterable[SessionEventRow],
    usage_by_key: dict[str, TokenUsage],
) -> SessionReport:
    """Aggregate a session's journal rows into a :class:`SessionReport`.

    ``events`` are rows with ``ts`` / ``event`` / ``client`` / ``model`` / ``execution_key``
    (oldest first); ``usage_by_key`` maps an execution key to its :class:`TokenUsage`.
    """
    models: dict[tuple, dict[str, int]] = {}
    days: dict[str, dict[str, int]] = {}
    invocations = executions = hits = unknown = 0

    for row in events:
        invocations += 1
        day = (row.ts or "")[:10]
        d = days.setdefault(day, {"invocations": 0, "executions": 0, "hits": 0})
        d["invocations"] += 1
        m = models.setdefault(
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

        if row.event == _HIT:
            hits += 1
            d["hits"] += 1
            m["hits"] += 1
            saved = _tokens(usage)
            if saved is not None:
                m["saved"] += saved
        elif row.event in EXECUTED_EVENTS:
            executions += 1
            d["executions"] += 1
            m["executions"] += 1
            if usage is not None and _tokens(usage) is not None:
                m["in"] += usage.input_tokens or 0
                m["out"] += usage.output_tokens or 0
                m["cache_read"] += usage.cache_read_tokens or 0
                m["cache_write"] += usage.cache_write_tokens or 0
                m["reasoning"] += usage.reasoning_tokens or 0
            else:
                unknown += 1

    by_model = [
        ModelUsage(
            client=client,
            model=model,
            spent_input=v["in"],
            spent_output=v["out"],
            cache_read_tokens=v["cache_read"],
            cache_write_tokens=v["cache_write"],
            reasoning_tokens=v["reasoning"],
            saved_tokens=v["saved"],
            executions=v["executions"],
            hits=v["hits"],
        )
        for (client, model), v in sorted(models.items())
    ]
    by_day = [
        DayActivity(
            day=day, invocations=v["invocations"], executions=v["executions"], hits=v["hits"]
        )
        for day, v in sorted(days.items())
    ]
    return SessionReport(
        session_id=session_id,
        invocations=invocations,
        executions=executions,
        hits=hits,
        unknown_usage=unknown,
        span_start=by_day[0].day if by_day else None,
        span_end=by_day[-1].day if by_day else None,
        by_model=by_model,
        by_day=by_day,
    )
