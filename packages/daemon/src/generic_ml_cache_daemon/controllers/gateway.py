# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Route: POST /gateway/claude/{session_id}/v1/messages — Anthropic Messages API caching proxy."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from generic_ml_cache_core.application.domain.model.gateway.gateway_request import GatewayRequest
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_command import (
    RunMlGatewayCommand,
)
from starlette.responses import Response

from generic_ml_cache_daemon.presenters.gateway import MessagesRequest

router = APIRouter(prefix="/gateway/claude")

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"  # NOSONAR
_HOP_BY_HOP = frozenset(
    ["host", "connection", "content-length", "accept-encoding", "transfer-encoding"]
)


@router.get("/{session_id}", include_in_schema=False)
@router.head("/{session_id}", include_in_schema=False)
async def gateway_probe(session_id: str) -> dict:
    """Connectivity probe — Claude Code sends HEAD/GET here on startup."""
    return {}


@router.post("/{session_id}/v1/messages")
async def proxy_messages(session_id: str, body: MessagesRequest, request: Request) -> Response:
    """Cache-aware pass-through proxy for the Anthropic Messages API.

    The gmlcache session ID is embedded in the URL path so the daemon stays
    stateless — no --session flag needed at startup, and multiple sessions can
    share the same daemon simultaneously.
    """
    forward_headers = {k: v for k, v in request.headers.items() if k not in _HOP_BY_HOP}
    api_token = request.headers.get("x-api-key", "")
    # Forward the caller's body verbatim — every field, validated or not, is kept
    # (extra="allow") so nothing is dropped upstream or from the cache key. The
    # gmlcache session id rides in the URL path, not the upstream body, so it is
    # excluded; max_tokens carries its validated default when the caller omits it.
    gateway_request = GatewayRequest(body=body.model_dump(exclude={"session_id"}))
    command = RunMlGatewayCommand(
        gateway_request=gateway_request,
        api_token=api_token,
        target_url=_ANTHROPIC_MESSAGES_URL,
        session_id=session_id,
        forward_headers=forward_headers,
    )
    wired = request.app.state.wired
    loop = asyncio.get_event_loop()
    gateway_response = await loop.run_in_executor(None, wired.run_gateway.execute, command)
    return Response(
        content=gateway_response.response_body_bytes,
        status_code=gateway_response.status_code,
        media_type="application/json",
        headers={"x-cache-hit": "true" if gateway_response.cache_hit else "false"},
    )
