# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Session-report domain DTOs: the roll-up of a session's activity.

Pure value objects (no ports, no I/O). They live in the domain so an inbound
port can return them without the port ring importing a use case. The projection
that builds them from journal rows is ``domain.service.session_report.build_session_report``.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    by_model: tuple[ModelUsage, ...]
    by_day: tuple[DayActivity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_model", tuple(self.by_model))
        object.__setattr__(self, "by_day", tuple(self.by_day))

    @property
    def day_count(self) -> int:
        return len(self.by_day)


@dataclass(frozen=True)
class TagSessionReport:
    """One report aggregated across every session carrying a tag."""

    tag: str
    report: SessionReport
    session_count: int
