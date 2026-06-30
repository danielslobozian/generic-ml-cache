# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Session report presenters — render a session report as text or JSON."""

from __future__ import annotations

from generic_ml_cache_cli.presenters.shared import _activity_bar, _comma


def _render_session_report(report, tags: list | None = None) -> str:
    lines = [f"session     : {report.session_id}"]
    if tags:
        lines.append(f"tags        : {', '.join(sorted(tags))}")
    if report.span_start:
        span = (
            report.span_start
            if report.day_count == 1
            else f"{report.span_start} → {report.span_end}"
        )
        plural = "" if report.day_count == 1 else "s"
        lines.append(f"span        : {span}  ({report.day_count} day{plural})")
    lines.append(
        f"invocations : {report.invocations}   "
        f"executions : {report.executions}   hits : {report.hits}"
    )
    if report.unknown_usage:
        lines.append(f"unknown     : {report.unknown_usage} execution(s) reported no usage")
    if report.by_model:
        lines.append("")
        lines.append("by provider / model:")
        for m in report.by_model:
            lines.append(
                f"  {m.client + ' / ' + m.model:<16} spent {_comma(m.spent_tokens):>9} tok"
                f" (in {_comma(m.spent_input):>8} · out {_comma(m.spent_output):>7})"
                f"   saved {_comma(m.saved_tokens):>9} tok   {m.executions} exec · {m.hits} hit"
            )
    if report.by_day:
        lines.append("")
        lines.append("by day (activity):")
        maxinv = max(d.invocations for d in report.by_day)
        for d in report.by_day:
            lines.append(
                f"  {d.day}  {_activity_bar(d.invocations, maxinv)}  {d.invocations:>3} calls"
                f"   ({d.executions} exec · {d.hits} hit)"
            )
    return "\n".join(lines)


def _session_report_json(report, tags: list) -> dict:
    return {
        "session": report.session_id,
        "tags": tags,
        "invocations": report.invocations,
        "executions": report.executions,
        "hits": report.hits,
        "unknown_usage": report.unknown_usage,
        "span": {"start": report.span_start, "end": report.span_end, "days": report.day_count},
        "by_model": [
            {
                "client": m.client,
                "model": m.model,
                "spent_input": m.spent_input,
                "spent_output": m.spent_output,
                "spent_tokens": m.spent_tokens,
                "saved_tokens": m.saved_tokens,
                "executions": m.executions,
                "hits": m.hits,
            }
            for m in report.by_model
        ],
        "by_day": [
            {
                "day": d.day,
                "invocations": d.invocations,
                "executions": d.executions,
                "hits": d.hits,
            }
            for d in report.by_day
        ],
    }
