# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /executions, /stats, /purge."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request  # noqa: F401

from generic_ml_cache_daemon.models.execution import (
    ExecutionListResponse,
    ExecutionSummaryResponse,
    GlobalStatsResponse,
    PurgeBody,
    PurgeByAll,
    PurgeByKey,
    PurgeBySession,
    PurgeBySessionTag,
    PurgeByTag,
    PurgeResponse,
)

router = APIRouter()


@router.get("/executions", response_model=ExecutionListResponse)
def list_executions(request: Request) -> ExecutionListResponse:
    """Return all current (servable) executions."""
    summaries = request.app.state.wired.repository.current_execution_summaries()
    items = [
        ExecutionSummaryResponse(
            execution_key=s.execution_key, kind=s.kind, client=s.client, model=s.model
        )
        for s in summaries
    ]
    return ExecutionListResponse(executions=items, total=len(items))


@router.get("/executions/{key}", response_model=ExecutionSummaryResponse)
def get_execution(key: str, request: Request) -> ExecutionSummaryResponse:
    """Return the execution whose key equals or starts with ``key``."""
    summaries = request.app.state.wired.repository.current_execution_summaries()
    # exact match first, then prefix
    exact = [s for s in summaries if s.execution_key == key]
    if exact:
        s = exact[0]
        return ExecutionSummaryResponse(
            execution_key=s.execution_key, kind=s.kind, client=s.client, model=s.model
        )
    prefix_matches = [s for s in summaries if s.execution_key.startswith(key)]
    if not prefix_matches:
        raise HTTPException(status_code=404, detail=f"execution {key!r} not found")
    if len(prefix_matches) > 1:
        raise HTTPException(
            status_code=409,
            detail=f"ambiguous key prefix {key!r} matches {len(prefix_matches)} executions",
        )
    s = prefix_matches[0]
    return ExecutionSummaryResponse(
        execution_key=s.execution_key, kind=s.kind, client=s.client, model=s.model
    )


@router.get("/stats", response_model=GlobalStatsResponse)
def get_stats(request: Request) -> GlobalStatsResponse:
    """Return global store statistics."""
    wired = request.app.state.wired
    summaries = wired.repository.current_execution_summaries()
    return GlobalStatsResponse(
        executions=len(summaries),
        event_counts=wired.metrics.event_counts(),
    )


@router.post("/purge", response_model=PurgeResponse)
def purge(body: Annotated[PurgeBody, Body(discriminator="by")], request: Request) -> PurgeResponse:
    """Purge (soft-delete) executions by scope."""
    purge_service = request.app.state.wired.purge
    if isinstance(body, PurgeByAll):
        report = purge_service.purge_all()
    elif isinstance(body, PurgeByKey):
        report = purge_service.purge_one(body.target)
    elif isinstance(body, PurgeByTag):
        report = purge_service.purge_by_tag(body.target)
    elif isinstance(body, PurgeBySession):
        report = purge_service.purge_by_session(body.target)
    elif isinstance(body, PurgeBySessionTag):
        report = purge_service.purge_by_session_tag(body.target)
    else:  # pragma: no cover
        raise HTTPException(status_code=422, detail="unsupported purge scope")
    return PurgeResponse(
        executions_removed=report.executions_removed,
        bytes_freed=report.bytes_freed,
        blobs_removed=report.blobs_removed,
    )
