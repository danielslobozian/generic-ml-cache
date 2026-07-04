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
        status_code, response_body = self._forward(http_request, request.timeout)
        return self._to_answer(status_code, response_body)

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
    ) -> tuple[int, bytes]:
        """POST upstream and return ``(status, raw body)`` for any HTTP response —
        including a non-2xx, which is returned (not raised) so the gateway forwards it
        verbatim. Only a genuine network/timeout failure is translated (W16)."""
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with urllib.request.urlopen(  # noqa: S310 — operator-configured upstream, https
                http_request, timeout=effective_timeout
            ) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as http_error:
            return http_error.code, http_error.read()
        except (urllib.error.URLError, TimeoutError) as network_error:
            raise ProviderApiError(
                provider=self.name, status_code=_NO_STATUS, body=str(network_error)
            ) from network_error

    def _to_answer(self, status_code: int, response_body: bytes) -> ClientAnswer:
        if status_code == _HTTP_OK:
            # A 200 is cached and its usage parsed, so it must be the clean UTF-8 JSON
            # the Messages contract promises. A non-UTF-8 200 is a broken upstream/proxy
            # — surface it as ProviderProtocolError (W19) so it is never cached and never
            # a raw UnicodeDecodeError crashing the driver into a 500 (X3).
            return ClientAnswer(
                exit_code=0,
                stdout=self._decode_ok_body(response_body),
                token_usage=self._parse_usage(response_body),
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

    def _parse_usage(self, response_body: bytes) -> TokenUsage | None:
        """Map the Anthropic usage block to TokenUsage (W14). Usage accounting must
        never break the relay, so a malformed body just yields no usage."""
        try:
            usage = json.loads(response_body).get("usage", {})
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
            return None
        return TokenUsage(
            input_tokens=int_or_none(usage.get("input_tokens")),
            output_tokens=int_or_none(usage.get("output_tokens")),
            cache_read_tokens=int_or_none(usage.get("cache_read_input_tokens")),
            cache_write_tokens=int_or_none(usage.get("cache_creation_input_tokens")),
            reasoning_tokens=None,  # Anthropic folds thinking into output_tokens
            cost_usd=None,  # Anthropic API does not report cost per call
            raw=dict(usage),
        )
