# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Route: POST /gateway/claude/{session_id}/v1/messages — Anthropic Messages caching proxy.

The daemon *is* the gateway: it maps an Anthropic-Messages HTTP request onto the
library's ``run_ml_execution`` inbound port with an ``API_PASSTHROUGH`` command, so the
caching / recording / hit-check all come from the one shared cache protocol. The raw
request body is forwarded and keyed verbatim (W11); the verbatim relay wired in the
composition root does the actual upstream call and reports the real status (W15).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from starlette.responses import Response

router = APIRouter(prefix="/gateway/claude")

#: The client name the gateway relays through; the composition root wires the verbatim
#: ``AnthropicSubscriptionRelayAdapter`` under this name (the end-to-end gateway tests
#: fail loudly if the two ever drift, since run_ml would raise UnknownClient).
_RELAY_CLIENT = "anthropic-subscription"
_HTTP_OK = 200
_BAD_GATEWAY = 502
_JSON_MEDIA_TYPE = "application/json"
_VALIDATION_STATUS = 422


@router.get("/{session_id}", include_in_schema=False)
@router.head("/{session_id}", include_in_schema=False)
async def gateway_probe(session_id: str) -> dict[str, str]:
    """Connectivity probe — Claude Code sends HEAD/GET here on startup."""
    return {}


@router.post("/{session_id}/v1/messages")
async def proxy_messages(session_id: str, request: Request) -> Response:
    """Cache-aware pass-through proxy for the Anthropic Messages API.

    The gmlcache session ID rides in the URL path so the daemon stays stateless — no
    ``--session`` flag at startup, and many sessions can share one daemon. The caller's
    body is forwarded and keyed byte-for-byte; only a copy is validated (W11).
    """
    raw_body = await request.body()
    _reject_malformed(raw_body)
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.API_PASSTHROUGH,
        client=_RELAY_CLIENT,
        model="",
        raw_body=raw_body,
        # Forwarded verbatim; the relay drops connection-scoped hops case-insensitively.
        forward_headers=tuple(request.headers.items()),
        session_id=session_id,
    )
    wired = request.app.state.wired
    loop = asyncio.get_event_loop()
    execution = await loop.run_in_executor(None, wired.run_ml.execute, command)
    status_code, response_body = _to_http_response(execution)
    return Response(content=response_body, status_code=status_code, media_type=_JSON_MEDIA_TYPE)


def _reject_malformed(raw_body: bytes) -> None:
    """Fast local reject of a body that cannot be a Messages request (W11 — validate a
    *copy*; the raw bytes are still what gets forwarded and keyed, never this parse)."""
    try:
        parsed = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=_VALIDATION_STATUS, detail="request body is not valid JSON"
        ) from exc
    if not isinstance(parsed, dict) or "model" not in parsed:
        raise HTTPException(
            status_code=_VALIDATION_STATUS, detail="request body must include 'model'"
        )


def _to_http_response(execution: MlExecution) -> tuple[int, bytes]:
    """Map the recorded/served execution back to the wire response: the STDOUT artifact
    is the verbatim upstream body; a SUCCESS is a 200 (only a 200 is cached), a failure
    carries the real upstream status in its exit code, forwarded verbatim and uncached."""
    response_body = _stdout_bytes(execution)
    if execution.execution_state is ExecutionState.SUCCESS:
        return _HTTP_OK, response_body
    upstream_status = execution.failure.exit_code if execution.failure else None
    return upstream_status or _BAD_GATEWAY, response_body


def _stdout_bytes(execution: MlExecution) -> bytes:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT and artifact.content is not None:
            return artifact.content
    return b""
