# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AnthropicSubscriptionRelayAdapter: a verbatim API-passthrough relay to Anthropic.

The relay backing the caching HTTP gateway. Unlike ``AnthropicDirectAdapter`` (which
builds a structured request and distils the reply to text), this forwards the raw
request bytes and returns the response **verbatim** — the full Messages JSON
envelope, thinking blocks and all — because the caller (the daemon gateway) hands it
straight back to Claude Code. Auth rides in the forwarded headers (the caller's
subscription token), not an ``x-api-key``/env key. The upstream endpoint is baked in
(operator-configured, trusted-input-only — W9).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, cast

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.api_passthrough_request import (
    ApiPassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none
from generic_ml_cache_core.application.port.outbound.api_passthrough_runner_port import (
    ApiPassthroughRunnerPort,
)
from generic_ml_cache_core.common.errors import ProviderApiError, ProviderProtocolError

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"  # NOSONAR — operator-configured upstream
_HTTP_OK = 200
#: Upper bound on the body snippet carried in a ProviderProtocolError, so a broken
#: upstream body cannot flood a diagnostic log (matches the W19 bounding).
_BODY_SNIPPET_LIMIT = 500
#: A network failure carries no HTTP status; ProviderApiError.status_code needs an
#: int, so 0 means "no response reached us" (mapped to 502 by the daemon).
_NO_STATUS = 0
_JSON_CONTENT_TYPE = "application/json"
#: Header names dropped before forwarding upstream, compared case-insensitively (W8):
#: connection-scoped hops and the content-type we set ourselves.
_SKIP_HEADERS = frozenset(
    {
        "host",
        "connection",
        "content-length",
        "accept-encoding",
        "transfer-encoding",
        "content-type",
    }
)


class AnthropicSubscriptionRelayAdapter(ApiPassthroughRunnerPort):
    """Forward a raw Anthropic Messages request verbatim and return the wire response.

    The answer's ``exit_code`` carries the upstream status (0 for a 200, otherwise the
    status itself), so the shared cache protocol caches only a 200 and returns any
    other status verbatim without caching (W13/W15). Network/timeout/TLS failures are
    translated to :class:`ProviderApiError` at this boundary (W16) — never leaked raw.
    """

    name = "anthropic-subscription"

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    @property
    def execution_kind(self) -> ExecutionKind:
        """Its registry identity — the gateway dispatches API_PASSTHROUGH to it."""
        return ExecutionKind.API_PASSTHROUGH

    def execute_api_passthrough(self, request: ApiPassthroughRequest) -> ClientAnswer:
        http_request = urllib.request.Request(  # noqa: S310 — operator-configured upstream, https
            _MESSAGES_URL,
            data=request.raw_body,
            headers=self._upstream_headers(request.forward_headers),
            method="POST",
        )
        status_code, content_type, response_body = self._forward(http_request, request.timeout)
        return self._to_answer(status_code, content_type, response_body)

    def _upstream_headers(self, forward_headers: Mapping[str, str]) -> dict[str, str]:
        """The caller's headers forwarded verbatim (auth included), minus the
        connection-scoped hops, with our own JSON content-type — all compared
        case-insensitively so a title-case ``Host``/``Content-Type`` is caught (W8)."""
        upstream = {
            name: value
            for name, value in forward_headers.items()
            if name.lower() not in _SKIP_HEADERS
        }
        upstream["content-type"] = _JSON_CONTENT_TYPE
        return upstream

    def _forward(
        self, http_request: urllib.request.Request, timeout: float | None
    ) -> tuple[int, str, bytes]:
        """POST upstream and return ``(status, content-type, raw body)`` for any HTTP
        response — including a non-2xx, which is returned (not raised) so the gateway
        forwards it verbatim. The content-type drives usage parsing (a single JSON body
        vs an SSE stream). Only a genuine network/timeout failure is translated (W16)."""
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with urllib.request.urlopen(  # noqa: S310 — operator-configured upstream, https
                http_request, timeout=effective_timeout
            ) as response:
                return response.status, self._content_type(response), response.read()
        except urllib.error.HTTPError as http_error:
            return http_error.code, self._content_type(http_error), http_error.read()
        except (urllib.error.URLError, TimeoutError) as network_error:
            raise ProviderApiError(
                provider=self.name, status_code=_NO_STATUS, body=str(network_error)
            ) from network_error

    @staticmethod
    def _content_type(response: object) -> str:
        """The response's declared media type, always a ``str`` — a missing or odd
        header yields ``""`` (treated as a non-streaming JSON body downstream)."""
        try:
            value = response.headers.get("content-type", "")  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            return ""
        return value if isinstance(value, str) else ""

    def _to_answer(self, status_code: int, content_type: str, response_body: bytes) -> ClientAnswer:
        if status_code == _HTTP_OK:
            # A 200 is cached and usage-parsed. The body is UTF-8 text — a single JSON
            # envelope, or an SSE event stream when Claude Code streams; content_type
            # selects the usage parser. A non-UTF-8 200 is a broken upstream/proxy —
            # surface it as ProviderProtocolError (W19) so it is never cached and never
            # a raw UnicodeDecodeError crashing the driver into a 500 (X3).
            return ClientAnswer(
                exit_code=0,
                stdout=self._decode_ok_body(response_body),
                token_usage=self._parse_usage(response_body, content_type),
            )
        # A non-2xx body is relayed verbatim and NOT cached; decode it leniently so a
        # binary / non-UTF-8 proxy error page forwards (replacement chars) instead of
        # crashing the relay. The bytes-verbatim passthrough is declined for now — the
        # happy path is UTF-8 (documented assumption); this is only its error edge (X3).
        return ClientAnswer(
            exit_code=status_code,
            stdout=response_body.decode("utf-8", errors="replace"),
            token_usage=None,
        )

    def _decode_ok_body(self, response_body: bytes) -> str:
        try:
            return response_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderProtocolError(
                provider=self.name,
                status_code=_HTTP_OK,
                body=response_body[:_BODY_SNIPPET_LIMIT].decode("utf-8", errors="replace"),
            ) from exc

    def _parse_usage(self, response_body: bytes, content_type: str) -> TokenUsage | None:
        """Map the Anthropic usage to TokenUsage, dispatched by the declared media type:
        a single JSON body, or an SSE stream (Claude Code streams — usage is split across
        ``message_start`` / ``message_delta`` events). The event and field shapes are
        Anthropic wire specifics, so they live here in the adapter, never in the port.
        Usage accounting must never break the relay (W14), so a malformed body yields no
        usage."""
        if "text/event-stream" in content_type.lower():
            return self._parse_usage_sse(response_body)
        return self._parse_usage_json(response_body)

    def _parse_usage_json(self, response_body: bytes) -> TokenUsage | None:
        """Usage from a single JSON Messages envelope (the non-streaming response)."""
        try:
            usage = json.loads(response_body).get("usage")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
            return None
        return self._usage_from_block(usage)

    def _parse_usage_sse(self, response_body: bytes) -> TokenUsage | None:
        """Usage from an Anthropic SSE stream: input / cache tokens arrive in
        ``message_start.message.usage`` and the final ``output_tokens`` in the last
        ``message_delta.usage``. Merge them (later events overlay earlier), scanning the
        whole buffered stream — which is all we have, since the relay reads to completion,
        so no incremental-streaming machinery is needed here. Any malformed stream yields
        no usage (W14)."""
        merged: dict[str, Any] = {}
        try:
            text = response_body.decode("utf-8", errors="replace")
        except (AttributeError, TypeError):
            return None
        for raw_line in text.splitlines():
            block = self._sse_line_usage(raw_line)
            if block:
                merged.update(block)
        return self._usage_from_block(merged) if merged else None

    @staticmethod
    def _sse_line_usage(raw_line: str) -> dict[str, Any]:
        """The usage mapping carried by one SSE ``data:`` line — nested under ``message``
        for a ``message_start``, top-level for a ``message_delta`` — or ``{}`` for any
        other, keep-alive, ``[DONE]``, or unparseable line (W14)."""
        line = raw_line.strip()
        if not line.startswith("data:"):
            return {}
        payload = line[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            return {}
        try:
            event = json.loads(payload)
            usage = event.get("message", {}).get("usage") or event.get("usage")
        except (json.JSONDecodeError, AttributeError, TypeError):
            return {}
        return cast("dict[str, Any]", usage) if isinstance(usage, dict) else {}

    def _usage_from_block(self, usage: Any) -> TokenUsage | None:
        """Build TokenUsage from an Anthropic usage mapping — the same field names appear
        in the single-JSON body and the SSE events. A non-mapping yields ``None`` (W14)."""
        if not isinstance(usage, dict):
            return None
        block = cast("dict[str, Any]", usage)
        return TokenUsage(
            input_tokens=int_or_none(block.get("input_tokens")),
            output_tokens=int_or_none(block.get("output_tokens")),
            cache_read_tokens=int_or_none(block.get("cache_read_input_tokens")),
            cache_write_tokens=int_or_none(block.get("cache_creation_input_tokens")),
            reasoning_tokens=None,  # Anthropic folds thinking into output_tokens
            cost_usd=None,  # Anthropic API does not report cost per call
            raw=dict(block),
        )
