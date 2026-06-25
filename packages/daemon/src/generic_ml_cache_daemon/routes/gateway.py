# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Route: POST /gateway/claude/v1/messages — Anthropic Messages API caching proxy.

Scope for 0.13.0: single-user-turn conversations only (one role=user message in
the messages array). Multi-turn support requires thread-aware context handling and
is deferred to a future element.
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from generic_ml_cache_core.adapter.inbound.composition import resolve_execution_kind
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_state import (
    ExecutionState,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)

from generic_ml_cache_daemon.models.gateway import (
    ContentBlock,
    MessagesRequest,
    MessagesResponse,
)

router = APIRouter(prefix="/gateway/claude")

_STDOUT = ArtifactType.STDOUT
_CLIENT = "anthropic"


def _extract_stdout(execution: Any) -> str:
    for artifact in execution.artifacts:
        if artifact.artifact_type is _STDOUT and artifact.content is not None:
            try:
                return artifact.content.decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover
                return ""
    return ""


def _build_usage(execution: Any) -> dict:
    if execution.token_usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    tu = execution.token_usage
    return {
        "input_tokens": tu.input_tokens or 0,
        "output_tokens": tu.output_tokens or 0,
        "cache_read_input_tokens": getattr(tu, "cache_read_tokens", None) or 0,
        "cache_creation_input_tokens": getattr(tu, "cache_write_tokens", None) or 0,
    }


@router.post(
    "/v1/messages",
    responses={
        422: {"description": "Multi-turn request (only single-turn supported in 0.13.0)"},
        502: {"description": "Upstream Anthropic call failed"},
        503: {"description": "Anthropic adapter not available"},
    },
)
async def proxy_messages(body: MessagesRequest, request: Request) -> MessagesResponse:
    """Cache-aware proxy for POST https://api.anthropic.com/v1/messages.

    Only single-turn conversations (one user message) are supported in 0.13.0.
    Multi-turn requests (messages with more than one entry) return HTTP 422.
    """
    user_messages = [m for m in body.messages if m.role == "user"]
    if len(user_messages) != 1 or len(body.messages) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "The gateway currently supports single-turn requests only "
                "(one role=user message, no prior assistant turns). "
                "Multi-turn support is planned."
            ),
        )

    try:
        kind = resolve_execution_kind(_CLIENT)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    command = RunMlExecutionCommand(
        execution_kind=kind,
        client=_CLIENT,
        model=body.model,
        prompt=user_messages[0].content,
        user_system_prompt=body.system,
        session_id=body.session_id,
    )

    wired = request.app.state.wired
    loop = asyncio.get_event_loop()
    execution = await loop.run_in_executor(None, wired.run_ml.execute, command)

    if execution.execution_state is ExecutionState.FAILED:
        raise HTTPException(
            status_code=502,
            detail="upstream Anthropic call failed",
        )

    stdout = _extract_stdout(execution)
    cache_hit = execution.execution_state is ExecutionState.SUCCESS and bool(stdout)

    return MessagesResponse(
        id=f"msg_{secrets.token_hex(12)}",
        content=[ContentBlock(text=stdout)],
        model=body.model,
        usage=_build_usage(execution),
        x_cache_hit=cache_hit,
    )
