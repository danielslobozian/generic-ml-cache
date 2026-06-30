# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /jobs — submit detached background executions and stream/poll their status."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType

from generic_ml_cache_daemon.controllers.run import _build_command, _extract_artifact
from generic_ml_cache_daemon.jobs import Job, JobState
from generic_ml_cache_daemon.presenters.job import JobResponse, JobSubmitBody

router = APIRouter(prefix="/jobs")

_STDOUT = ArtifactType.STDOUT
_STDERR = ArtifactType.STDERR
_SSE_POLL_INTERVAL = 0.1


def _job_to_response(job: Job) -> JobResponse:
    execution_key: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    if job.execution is not None:
        execution_key = job.execution.call_identity.generate_key()
        stdout = _extract_artifact(job.execution, _STDOUT)
        stderr = _extract_artifact(job.execution, _STDERR)
    return JobResponse(
        job_id=job.job_id,
        state=job.state.value,
        execution_key=execution_key,
        stdout=stdout,
        stderr=stderr,
        error=job.error,
    )


@router.post("", status_code=202)
def submit_job(body: JobSubmitBody, request: Request) -> JobResponse:
    """Submit an execution to run in the background. Returns immediately with
    a job_id in 'pending' state."""
    command = _build_command(body, request.app.state.whitelist)  # type: ignore[arg-type]
    wired = request.app.state.wired
    registry = request.app.state.job_registry
    job = registry.submit(wired.run_ml.execute, command)
    return _job_to_response(job)


@router.get("")
def list_jobs(request: Request) -> Dict[str, Any]:
    """Return all known job IDs."""
    registry = request.app.state.job_registry
    return {"job_ids": registry.list_ids()}


@router.get("/{job_id}", responses={404: {"description": "Job not found"}})
def get_job(job_id: str, request: Request) -> JobResponse:
    """Return the current status of a job."""
    registry = request.app.state.job_registry
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return _job_to_response(job)


@router.get("/{job_id}/stream", responses={404: {"description": "Job not found"}})
async def stream_job(job_id: str, request: Request) -> Any:
    """SSE stream for a job. Emits a 'status' event every 100ms until the job
    completes, then a final 'complete' or 'error' event."""
    from sse_starlette.sse import EventSourceResponse

    registry = request.app.state.job_registry
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")

    async def generator() -> AsyncIterator[Dict[str, str]]:
        while job.state not in (JobState.DONE, JobState.ERROR):  # pragma: no cover
            yield {"data": json.dumps({"type": "status", "state": job.state.value})}
            await asyncio.sleep(_SSE_POLL_INTERVAL)
        response = _job_to_response(job)
        event_type = "complete" if job.state is JobState.DONE else "error"
        yield {"data": json.dumps({"type": event_type, **response.model_dump()})}

    return EventSourceResponse(generator())
