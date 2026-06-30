# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Route: POST /run — synchronous execution or SSE stream, content-negotiated."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from generic_ml_cache_bootstrap.discovery.composition import execution_kind_for
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_state import (
    ExecutionState,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from sse_starlette.sse import EventSourceResponse

from generic_ml_cache_daemon.presenters.run import RunBody, RunResponse

router = APIRouter()

_STDOUT = ArtifactType.STDOUT
_STDERR = ArtifactType.STDERR


def _build_command(body: RunBody, whitelist: frozenset[str] | None) -> RunMlExecutionCommand:
    # Resolve the kind over the *whitelisted* catalog: an unknown or non-whitelisted
    # client raises UnknownClient here, which the CacheError handler maps to 400 —
    # the whitelist is enforced at /run, not only at /health.
    kind = execution_kind_for(body.client, whitelist)
    return RunMlExecutionCommand(
        execution_kind=kind,
        client=body.client,
        model=body.model,
        effort=body.effort,
        prompt=body.prompt,
        context=body.context,
        tags=body.tags,
        session_id=body.session_id,
    )


def _extract_artifact(execution: MlExecution, artifact_type: ArtifactType) -> str | None:
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type and artifact.content is not None:
            try:
                return artifact.content.decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover
                return None
    return None


def _was_cache_hit(execution: MlExecution) -> bool:
    return execution.execution_state is ExecutionState.SUCCESS and any(
        a.artifact_type is _STDOUT for a in execution.artifacts
    )


def _to_response(execution: MlExecution, cache_hit: bool) -> RunResponse:
    key = execution.call_identity.generate_key()
    return RunResponse(
        execution_key=key,
        state=execution.execution_state.value,
        cache_hit=cache_hit,
        stdout=_extract_artifact(execution, _STDOUT),
        stderr=_extract_artifact(execution, _STDERR),
    )


def _to_dict(response: RunResponse) -> dict[str, Any]:
    return response.model_dump()


async def _run_in_thread(wired: Any, command: RunMlExecutionCommand) -> MlExecution:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, wired.run_ml.execute, command)


async def _sse_generator(
    wired: Any, command: RunMlExecutionCommand
) -> AsyncIterator[dict[str, str]]:
    yield {"data": json.dumps({"type": "accepted"})}
    execution = await _run_in_thread(wired, command)
    hit = _was_cache_hit(execution)
    response = _to_response(execution, hit)
    yield {"data": json.dumps({"type": "complete", **_to_dict(response)})}


@router.post("/run", responses={400: {"description": "Unknown or unsupported client"}})
async def run(body: RunBody, request: Request) -> Any:
    """Execute an ML call synchronously (JSON) or as a server-sent event stream (SSE).

    Content negotiation:
    - ``Accept: text/event-stream`` → SSE: an ``accepted`` event followed by a
      ``complete`` event when the execution finishes.
    - Any other ``Accept`` → JSON: blocks until the execution completes.
    """
    command = _build_command(body, request.app.state.whitelist)
    wired = request.app.state.wired

    if "text/event-stream" in request.headers.get("accept", ""):
        return EventSourceResponse(_sse_generator(wired, command))

    execution = await _run_in_thread(wired, command)
    cache_hit = _was_cache_hit(execution)
    response = _to_response(execution, cache_hit)
    return JSONResponse(content=_to_dict(response))
