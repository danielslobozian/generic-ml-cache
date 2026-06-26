# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Codex gateway probe routes — log every request, return 529."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter(prefix="/gateway/codex")

_log = logging.getLogger(__name__)

_529_BODY = json.dumps({"error": {"code": "probe", "message": "gmlcache probe — not forwarded"}}).encode()


async def _dump(label: str, request: Request) -> None:
    body = await request.body()
    _log.info(
        "[codex-probe] %s %s\n  headers: %s\n  body: %s",
        label,
        request.url.path,
        dict(request.headers),
        body.decode(errors="replace") if body else "(empty)",
    )


@router.get("/{session_id}/v1/models")
async def codex_models(session_id: str, request: Request) -> Response:
    await _dump("GET models", request)
    return Response(content=_529_BODY, status_code=529, media_type="application/json")


@router.post("/{session_id}/v1/responses")
async def codex_responses(session_id: str, request: Request) -> Response:
    await _dump("POST responses", request)
    return Response(content=_529_BODY, status_code=529, media_type="application/json")
