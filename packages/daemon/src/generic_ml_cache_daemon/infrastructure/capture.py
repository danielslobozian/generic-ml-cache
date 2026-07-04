# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Gateway capture middleware — record raw request/response pairs as NDJSON.

Activated by setting ``GMLCACHE_GATEWAY_CAPTURE=1`` before starting the daemon.
Only paths under ``/gateway/`` are captured; health, run, and session endpoints
are left untouched.

Each line in the output file is a self-contained JSON object:

    {
        "ts":               "<ISO-8601 UTC timestamp>",
        "method":           "POST",
        "path":             "/gateway/claude/v1/messages",
        "request_headers":  { ... },   // x-api-key and Authorization redacted
        "request_body":     { ... },   // parsed JSON, or raw string on failure
        "response_status":  200,
        "response_body":    { ... },   // parsed JSON, or raw string on failure
        "duration_ms":      42
    }

The capture file defaults to ``<store_root>/gateway-capture.ndjson`` but can be
overridden with ``GMLCACHE_GATEWAY_CAPTURE_PATH``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

_GATEWAY_PREFIX = "/gateway/"
_SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "chatgpt-account-id",
        "cookie",
        "session-id",
        "x-api-key",
    }
)
_REDACTED = "[REDACTED]"


class GatewayCaptureMiddleware(BaseHTTPMiddleware):
    """Append one NDJSON record per gateway request to a capture file.

    Non-gateway paths pass through without any overhead.
    A write failure never propagates to the caller — the daemon keeps serving.
    """

    def __init__(self, app: ASGIApp, *, capture_path: Path) -> None:
        super().__init__(app)
        self._capture_path = capture_path

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(_GATEWAY_PREFIX):
            return await call_next(request)
        return await self._capture_exchange(request, call_next)

    async def _capture_exchange(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        import time

        start_ns = time.monotonic_ns()
        request_body_bytes = await request.body()

        upstream_response = await call_next(request)
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        # BaseHTTPMiddleware always yields a streaming response, so its body is an
        # async chunk stream we must drain to read (and later re-emit) the bytes.
        body_iterator = cast(
            "AsyncIterator[bytes]", cast(StreamingResponse, upstream_response).body_iterator
        )
        response_body_bytes = b"".join([chunk async for chunk in body_iterator])

        self._append_record(
            request=request,
            request_body_bytes=request_body_bytes,
            response_status=upstream_response.status_code,
            response_body_bytes=response_body_bytes,
            duration_ms=duration_ms,
        )

        return Response(
            content=response_body_bytes,
            status_code=upstream_response.status_code,
            headers=dict(upstream_response.headers),
            media_type=upstream_response.media_type,
        )

    def _append_record(
        self,
        *,
        request: Request,
        request_body_bytes: bytes,
        response_status: int,
        response_body_bytes: bytes,
        duration_ms: int,
    ) -> None:
        record = {
            "ts": _utc_now(),
            "method": request.method,
            "path": str(request.url.path),
            "request_headers": _redact_headers(dict(request.headers)),
            "request_body": _decode_body(request_body_bytes),
            "response_status": response_status,
            "response_body": _decode_body(response_body_bytes),
            "duration_ms": duration_ms,
        }
        try:
            with self._capture_path.open("a", encoding="utf-8") as capture_file:
                capture_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # write failure must never take down the daemon


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        header_name: (_REDACTED if header_name.lower() in _SENSITIVE_HEADER_NAMES else header_value)
        for header_name, header_value in headers.items()
    }


def _decode_body(body_bytes: bytes) -> object:
    if not body_bytes:
        return None
    try:
        return json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body_bytes.decode("utf-8", errors="replace")
