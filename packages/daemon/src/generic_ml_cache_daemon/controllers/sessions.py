# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /sessions — CRUD, stats, spec, and tags."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from generic_ml_cache_core.application.domain.model.session.session_report import ModelUsage
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_command import (
    ClearSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_command import (
    GetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_command import (
    ReportForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_command import (
    ListSessionTagsCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_command import (
    TagSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_command import (
    UntagSessionCommand,
)

from generic_ml_cache_daemon.presenters.session import (
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


def _session_response(wired: Any, session_id: str) -> SessionResponse:
    return SessionResponse(
        session_id=session_id,
        tags=wired.session_tags.list_tags(ListSessionTagsCommand(session_id)),
        spec=_spec_to_body(wired.session_admin.get_spec(GetSessionSpecCommand(session_id))),
    )


@router.get("")
def list_sessions(request: Request) -> SessionListResponse:
    """Return all known session IDs."""
    wired = request.app.state.wired
    return SessionListResponse(session_ids=wired.session_admin.list_session_ids())


@router.post("", status_code=201)
def create_session(body: SessionCreateBody, request: Request) -> SessionResponse:
    """Create a new session, optionally seeding it with tags and/or a spec."""
    session_id = secrets.token_hex(8)
    wired = request.app.state.wired
    for tag in body.tags:
        wired.session_tags.tag(TagSessionCommand(session_id, tag))
    if body.spec is not None:
        spec = SessionSpec(client=body.spec.client, model=body.spec.model, effort=body.spec.effort)
        wired.session_admin.set_spec(SetSessionSpecCommand(session_id, spec))
    return _session_response(wired, session_id)


@router.get("/{session_id}", responses={404: {"description": "Session not found"}})
def get_session(session_id: str, request: Request) -> SessionResponse:
    """Return tags and spec for a session."""
    wired = request.app.state.wired
    tags = wired.session_tags.list_tags(ListSessionTagsCommand(session_id))
    spec = wired.session_admin.get_spec(GetSessionSpecCommand(session_id))
    if not tags and spec is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return SessionResponse(session_id=session_id, tags=tags, spec=_spec_to_body(spec))


@router.get("/{session_id}/stats")
def get_session_stats(session_id: str, request: Request) -> SessionStatsResponse:
    """Return call/hit statistics and per-model token usage for a session."""
    wired = request.app.state.wired
    report = wired.session_report.report_for_session(ReportForSessionCommand(session_id))
    hit_rate = round(report.hits / report.invocations, 4) if report.invocations > 0 else 0.0
    return SessionStatsResponse(
        session_id=session_id,
        tags=wired.session_tags.list_tags(ListSessionTagsCommand(session_id)),
        spec=_spec_to_body(wired.session_admin.get_spec(GetSessionSpecCommand(session_id))),
        calls=report.invocations,
        hits=report.hits,
        hit_rate=hit_rate,
        by_model=[_model_usage_body(mu) for mu in report.by_model],
    )


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
    wired = request.app.state.wired
    spec = SessionSpec(client=body.client, model=body.model, effort=body.effort)
    wired.session_admin.set_spec(SetSessionSpecCommand(session_id, spec))
    return _session_response(wired, session_id)


@router.delete("/{session_id}/spec", status_code=204)
def clear_session_spec(session_id: str, request: Request) -> None:
    """Remove the execution spec for a session (no-op if absent)."""
    request.app.state.wired.session_admin.clear_spec(ClearSessionSpecCommand(session_id))


@router.post("/{session_id}/tags", status_code=201)
def add_session_tag(session_id: str, body: TagBody, request: Request) -> SessionResponse:
    """Add a tag to a session."""
    wired = request.app.state.wired
    wired.session_tags.tag(TagSessionCommand(session_id, body.tag))
    return _session_response(wired, session_id)


@router.delete("/{session_id}/tags/{tag}", status_code=204)
def remove_session_tag(session_id: str, tag: str, request: Request) -> None:
    """Remove a tag from a session (no-op if tag is absent)."""
    request.app.state.wired.session_tags.untag(UntagSessionCommand(session_id, tag))
