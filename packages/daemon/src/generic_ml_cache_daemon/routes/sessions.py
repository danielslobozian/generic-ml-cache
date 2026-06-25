# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /sessions — CRUD, stats, spec, and tags."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.usecase.session_report import (
    ModelUsage,
    build_session_report,
)

from generic_ml_cache_daemon.models.session import (
    ModelUsageBody,
    SessionCreateBody,
    SessionListResponse,
    SessionResponse,
    SessionStatsResponse,
    SpecBody,
    TagBody,
)

router = APIRouter(prefix="/sessions")


def _spec_to_body(spec: SessionSpec | None) -> SpecBody | None:
    if spec is None:
        return None
    return SpecBody(client=spec.client, model=spec.model, effort=spec.effort)


def _session_response(metrics, session_id: str) -> SessionResponse:
    return SessionResponse(
        session_id=session_id,
        tags=metrics.session_tags(session_id),
        spec=_spec_to_body(metrics.session_spec(session_id)),
    )


@router.get("")
def list_sessions(request: Request) -> SessionListResponse:
    """Return all known session IDs."""
    metrics = request.app.state.wired.metrics
    return SessionListResponse(session_ids=metrics.list_session_ids())


@router.post("", status_code=201)
def create_session(body: SessionCreateBody, request: Request) -> SessionResponse:
    """Create a new session, optionally seeding it with tags and/or a spec."""
    session_id = secrets.token_hex(8)
    metrics = request.app.state.wired.metrics
    for tag in body.tags:
        metrics.add_session_tag(session_id, tag)
    if body.spec is not None:
        metrics.set_session_spec(
            session_id,
            SessionSpec(client=body.spec.client, model=body.spec.model, effort=body.spec.effort),
        )
    return _session_response(metrics, session_id)


@router.get("/{session_id}", responses={404: {"description": "Session not found"}})
def get_session(session_id: str, request: Request) -> SessionResponse:
    """Return tags and spec for a session."""
    metrics = request.app.state.wired.metrics
    tags = metrics.session_tags(session_id)
    spec = metrics.session_spec(session_id)
    if not tags and spec is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return SessionResponse(session_id=session_id, tags=tags, spec=_spec_to_body(spec))


@router.get("/{session_id}/stats")
def get_session_stats(session_id: str, request: Request) -> SessionStatsResponse:
    """Return call/hit statistics and per-model token usage for a session."""
    wired = request.app.state.wired
    events = wired.metrics.session_events(session_id)
    usage_by_key = _collect_usage(events, wired.repository)
    report = build_session_report(session_id, events, usage_by_key)
    hit_rate = round(report.hits / report.invocations, 4) if report.invocations > 0 else 0.0
    return SessionStatsResponse(
        session_id=session_id,
        tags=wired.metrics.session_tags(session_id),
        spec=_spec_to_body(wired.metrics.session_spec(session_id)),
        calls=report.invocations,
        hits=report.hits,
        hit_rate=hit_rate,
        by_model=[_model_usage_body(mu) for mu in report.by_model],
    )


def _collect_usage(events, repository) -> dict:
    usage_by_key = {}
    for execution_key in {row.execution_key for row in events if row.execution_key}:
        execution = repository.find_current(execution_key)
        if execution is not None:
            usage_by_key[execution_key] = execution.token_usage
    return usage_by_key


def _model_usage_body(mu: ModelUsage) -> ModelUsageBody:
    return ModelUsageBody(
        client=mu.client,
        model=mu.model,
        spent_input=mu.spent_input,
        spent_output=mu.spent_output,
        cache_read_tokens=mu.cache_read_tokens,
        cache_write_tokens=mu.cache_write_tokens,
        reasoning_tokens=mu.reasoning_tokens,
        saved_tokens=mu.saved_tokens,
        executions=mu.executions,
        hits=mu.hits,
    )


@router.put("/{session_id}/spec", status_code=200)
def set_session_spec(session_id: str, body: SpecBody, request: Request) -> SessionResponse:
    """Attach or replace the execution spec for a session."""
    metrics = request.app.state.wired.metrics
    metrics.set_session_spec(
        session_id,
        SessionSpec(client=body.client, model=body.model, effort=body.effort),
    )
    return _session_response(metrics, session_id)


@router.delete("/{session_id}/spec", status_code=204)
def clear_session_spec(session_id: str, request: Request) -> None:
    """Remove the execution spec for a session (no-op if absent)."""
    request.app.state.wired.metrics.clear_session_spec(session_id)


@router.post("/{session_id}/tags", status_code=201)
def add_session_tag(session_id: str, body: TagBody, request: Request) -> SessionResponse:
    """Add a tag to a session."""
    metrics = request.app.state.wired.metrics
    metrics.add_session_tag(session_id, body.tag)
    return _session_response(metrics, session_id)


@router.delete("/{session_id}/tags/{tag}", status_code=204)
def remove_session_tag(session_id: str, tag: str, request: Request) -> None:
    """Remove a tag from a session (no-op if tag is absent)."""
    request.app.state.wired.metrics.remove_session_tag(session_id, tag)
