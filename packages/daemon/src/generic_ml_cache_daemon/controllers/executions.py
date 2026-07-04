# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /executions, /stats, /purge."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from generic_ml_cache_core.application.port.inbound.purge.purge_all_command import PurgeAllCommand
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_command import (
    PurgeByKeyCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_command import (
    PurgeBySessionCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_command import (
    PurgeBySessionTagCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_command import (
    PurgeByTagCommand,
)
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_daemon.presenters.execution import (
    ExecutionListResponse,
    ExecutionSummaryResponse,
    GlobalStatsResponse,
    PurgeBody,
    PurgeByAll,
    PurgeByKey,
    PurgeBySession,
    PurgeByTag,
    PurgeResponse,
)

router = APIRouter()


@router.get("/executions")
def list_executions(request: Request) -> ExecutionListResponse:
    """Return all current (servable) executions."""
    wired: ApplicationApi = request.app.state.wired
    summaries = wired.list_execution_summaries.list_summaries()
    items = [
        ExecutionSummaryResponse(
            execution_key=s.execution_key, kind=s.kind, client=s.client, model=s.model
        )
        for s in summaries
    ]
    return ExecutionListResponse(executions=items, total=len(items))


@router.get(
    "/executions/{key}",
    responses={
        404: {"description": "Execution not found"},
        409: {"description": "Ambiguous key prefix matches multiple executions"},
    },
)
def get_execution(key: str, request: Request) -> ExecutionSummaryResponse:
    """Return the execution whose key equals or starts with ``key``."""
    wired: ApplicationApi = request.app.state.wired
    summaries = wired.list_execution_summaries.list_summaries()
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


@router.get("/stats")
def get_stats(request: Request) -> GlobalStatsResponse:
    """Return global store statistics."""
    wired: ApplicationApi = request.app.state.wired
    summaries = wired.list_execution_summaries.list_summaries()
    return GlobalStatsResponse(
        executions=len(summaries),
        event_counts=wired.event_counts.event_counts(),
    )


@router.post("/purge", responses={422: {"description": "Unsupported purge scope"}})
def purge(body: Annotated[PurgeBody, Body(discriminator="by")], request: Request) -> PurgeResponse:
    """Purge (soft-delete) executions by scope."""
    wired: ApplicationApi = request.app.state.wired
    if isinstance(body, PurgeByAll):
        report = wired.purge_all.purge_all(PurgeAllCommand())
    elif isinstance(body, PurgeByKey):
        report = wired.purge_by_key.purge_by_key(PurgeByKeyCommand(body.target))
    elif isinstance(body, PurgeByTag):
        report = wired.purge_by_tag.purge_by_tag(PurgeByTagCommand(body.target))
    elif isinstance(body, PurgeBySession):
        report = wired.purge_by_session.purge_by_session(PurgeBySessionCommand(body.target))
    else:
        # Exhaustive by construction: the Body(discriminator="by") union admits
        # exactly these five scopes, so the remaining case is PurgeBySessionTag —
        # any invalid discriminator is rejected as 422 before this handler runs.
        report = wired.purge_by_session_tag.purge_by_session_tag(
            PurgeBySessionTagCommand(body.target)
        )
    return PurgeResponse(
        executions_removed=report.executions_removed,
        bytes_freed=report.bytes_freed,
        blobs_removed=report.blobs_removed,
    )
