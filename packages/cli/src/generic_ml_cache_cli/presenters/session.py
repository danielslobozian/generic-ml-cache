# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Session report presenters — render a session report as text or JSON."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.session.session_report import SessionReport

from generic_ml_cache_cli.presenters.shared import activity_bar, comma


def render_session_report(report: SessionReport, tags: list[str] | None = None) -> str:
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
        for model_usage in report.by_model:
            lines.append(
                f"  {model_usage.client + ' / ' + model_usage.model:<16}"
                f" spent {comma(model_usage.spent_tokens):>9} tok"
                f" (in {comma(model_usage.spent_input):>8}"
                f" · out {comma(model_usage.spent_output):>7})"
                f"   saved {comma(model_usage.saved_tokens):>9} tok"
                f"   {model_usage.executions} exec · {model_usage.hits} hit"
            )
    if report.by_day:
        lines.append("")
        lines.append("by day (activity):")
        max_invocations = max(day_activity.invocations for day_activity in report.by_day)
        for day_activity in report.by_day:
            lines.append(
                f"  {day_activity.day}  {activity_bar(day_activity.invocations, max_invocations)}"
                f"  {day_activity.invocations:>3} calls"
                f"   ({day_activity.executions} exec · {day_activity.hits} hit)"
            )
    return "\n".join(lines)


def session_report_json(report: SessionReport, tags: list[str]) -> dict[str, object]:
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
                "client": model_usage.client,
                "model": model_usage.model,
                "spent_input": model_usage.spent_input,
                "spent_output": model_usage.spent_output,
                "spent_tokens": model_usage.spent_tokens,
                "saved_tokens": model_usage.saved_tokens,
                "executions": model_usage.executions,
                "hits": model_usage.hits,
            }
            for model_usage in report.by_model
        ],
        "by_day": [
            {
                "day": day_activity.day,
                "invocations": day_activity.invocations,
                "executions": day_activity.executions,
                "hits": day_activity.hits,
            }
            for day_activity in report.by_day
        ],
    }
