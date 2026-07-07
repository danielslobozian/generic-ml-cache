# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AnthropicSubscriptionRelayAdapter — the verbatim API-passthrough relay."""

from __future__ import annotations

import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from generic_ml_cache_core.application.domain.model.run.api_passthrough_request import (
    ApiPassthroughRequest,
)
from generic_ml_cache_core.common.errors import ProviderApiError, ProviderProtocolError

from generic_ml_cache_adapters.adapter.outbound.api.anthropic_subscription_relay_adapter import (
    AnthropicSubscriptionRelayAdapter,
)

_OK_BODY = b'{"content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":5,"output_tokens":7,"cache_read_input_tokens":2,"cache_creation_input_tokens":3}}'
_RAW_REQUEST = b'{"model":"claude-opus-4-8","messages":[{"role":"user","content":"hi"}]}'
_UPSTREAM_URL = "https://api.anthropic.com/v1/messages"


def _ok_response(
    body: bytes, status: int = 200, content_type: str = "application/json"
) -> MagicMock:
    response = MagicMock()
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)
    response.status = status
    response.read.return_value = body
    response.headers = {"content-type": content_type}
    return response


# A minimal but realistic Anthropic SSE stream (the shape Claude Code receives): input /
# cache tokens land in message_start.message.usage; the final output_tokens in message_delta.
_SSE_BODY = (
    b"event: message_start\n"
    b'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant",'
    b'"usage":{"input_tokens":817,"cache_creation_input_tokens":0,'
    b'"cache_read_input_tokens":10,"output_tokens":1}}}\n\n'
    b"event: content_block_delta\n"
    b'data: {"type":"content_block_delta","index":0,'
    b'"delta":{"type":"text_delta","text":"hi"}}\n\n'
    b"event: message_delta\n"
    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
    b'"usage":{"output_tokens":18}}\n\n'
    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)


def _request(**overrides) -> ApiPassthroughRequest:
    base = {"raw_body": _RAW_REQUEST, "forward_headers": {"authorization": "Bearer sub-tok"}}
    base.update(overrides)
    return ApiPassthroughRequest(**base)


class TestVerbatimResponse:
    def test_200_returns_body_verbatim_as_a_success(self):
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", return_value=_ok_response(_OK_BODY)):
            answer = adapter.execute_api_passthrough(_request())
        assert answer.exit_code == 0  # a 200 maps to a servable success
        assert answer.stdout.encode("utf-8") == _OK_BODY  # verbatim, envelope kept

    def test_200_maps_the_usage_block(self):
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", return_value=_ok_response(_OK_BODY)):
            answer = adapter.execute_api_passthrough(_request())
        assert answer.token_usage is not None
        assert answer.token_usage.input_tokens == 5
        assert answer.token_usage.output_tokens == 7
        assert answer.token_usage.cache_read_tokens == 2
        assert answer.token_usage.cache_write_tokens == 3

    def test_non_200_returns_the_real_status_and_body_verbatim(self):
        adapter = AnthropicSubscriptionRelayAdapter()
        error_body = b'{"error":"rate_limited"}'
        http_error = urllib.error.HTTPError(
            url=_UPSTREAM_URL,
            code=429,
            msg="Too Many Requests",
            hdrs=MagicMock(),
            fp=BytesIO(error_body),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            answer = adapter.execute_api_passthrough(_request())
        assert answer.exit_code == 429  # the real upstream status (W15), not a hardcoded 200
        assert answer.stdout.encode("utf-8") == error_body
        assert answer.token_usage is None  # only a 200 is accounted

    def test_non_200_non_utf8_body_forwards_lossily_without_crashing(self):
        # X3: a non-2xx proxy/error body that is not valid UTF-8 must forward (lossily,
        # with replacement chars) rather than crash the relay into a driver 500.
        adapter = AnthropicSubscriptionRelayAdapter()
        binary_body = b"\xff\xfe not valid utf-8 error page"
        http_error = urllib.error.HTTPError(
            url=_UPSTREAM_URL,
            code=502,
            msg="Bad Gateway",
            hdrs=MagicMock(),
            fp=BytesIO(binary_body),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            answer = adapter.execute_api_passthrough(_request())
        assert answer.exit_code == 502  # forwarded verbatim, not a crash
        assert "�" in answer.stdout  # the invalid bytes became the replacement char
        assert answer.token_usage is None

    def test_200_with_a_non_utf8_body_is_a_provider_protocol_error(self):
        # X3: a 200 is cached + usage-parsed, so a non-UTF-8 success is a broken upstream
        # — a ProviderProtocolError (never cached, never a raw UnicodeDecodeError).
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", return_value=_ok_response(b"\xff\xfe not utf8")):
            with pytest.raises(ProviderProtocolError):
                adapter.execute_api_passthrough(_request())

    def test_network_failure_is_translated_to_provider_api_error(self):
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(ProviderApiError) as raised:
                adapter.execute_api_passthrough(_request())
        assert raised.value.status_code == 0  # no response reached us -> daemon maps 502 (W16)

    def test_timeout_is_translated_to_provider_api_error(self):
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with pytest.raises(ProviderApiError):
                adapter.execute_api_passthrough(_request())


class TestStreamingUsage:
    """Claude Code streams (text/event-stream); usage is split across SSE events and
    must still be accounted (the gateway records the session's token spend)."""

    def _answer(self, body: bytes, content_type: str):
        adapter = AnthropicSubscriptionRelayAdapter()
        with patch(
            "urllib.request.urlopen",
            return_value=_ok_response(body, content_type=content_type),
        ):
            return adapter.execute_api_passthrough(_request())

    def test_sse_stream_parses_usage_across_events(self):
        answer = self._answer(_SSE_BODY, "text/event-stream")
        assert answer.exit_code == 0
        assert answer.token_usage is not None
        assert answer.token_usage.input_tokens == 817  # from message_start
        assert answer.token_usage.output_tokens == 18  # final message_delta, not the start's 1
        assert answer.token_usage.cache_read_tokens == 10
        assert answer.token_usage.cache_write_tokens == 0

    def test_sse_stream_body_is_returned_verbatim(self):
        # The stream is stored + replayed byte-for-byte, so a cache hit re-serves it whole.
        answer = self._answer(_SSE_BODY, "text/event-stream")
        assert answer.stdout.encode("utf-8") == _SSE_BODY

    def test_sse_content_type_with_charset_suffix_is_still_detected(self):
        answer = self._answer(_SSE_BODY, "text/event-stream; charset=utf-8")
        assert answer.token_usage is not None
        assert answer.token_usage.output_tokens == 18

    def test_last_message_delta_output_wins(self):
        body = (
            b"event: message_start\n"
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":5,"output_tokens":1}}}\n\n'
            b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":10}}\n\n'
            b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":42}}\n\n'
        )
        answer = self._answer(body, "text/event-stream")
        assert answer.token_usage is not None
        assert answer.token_usage.output_tokens == 42  # cumulative final, last delta wins

    def test_malformed_sse_yields_no_usage_without_crashing(self):
        # W14: usage accounting must never break the relay — a garbled stream is served
        # verbatim with no usage, not an exception.
        body = b"event: message_start\ndata: {not json at all\n\ngarbage line\n"
        answer = self._answer(body, "text/event-stream")
        assert answer.exit_code == 0
        assert answer.token_usage is None

    def test_json_content_type_still_uses_the_json_parser(self):
        # An SSE body would not parse as JSON, but a JSON content-type routes to the JSON
        # parser — content-type is the authoritative dispatch, not a body sniff.
        answer = self._answer(_OK_BODY, "application/json")
        assert answer.token_usage is not None
        assert answer.token_usage.input_tokens == 5


class TestForwarding:
    def _captured(self, request: ApiPassthroughRequest) -> dict:
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            captured["data"] = req.data
            captured["url"] = req.full_url
            return _ok_response(b"{}")

        adapter = AnthropicSubscriptionRelayAdapter()
        with patch("urllib.request.urlopen", fake_urlopen):
            adapter.execute_api_passthrough(request)
        return captured

    def test_forwards_the_raw_body_verbatim(self):
        assert self._captured(_request())["data"] == _RAW_REQUEST

    def test_posts_to_the_operator_configured_upstream(self):
        assert self._captured(_request())["url"] == _UPSTREAM_URL

    def test_forwards_the_caller_auth_header(self):
        # urllib title-cases header keys internally; the subscription token rides here.
        headers = self._captured(_request())["headers"]
        assert headers.get("Authorization") == "Bearer sub-tok"

    def test_strips_hop_by_hop_headers_case_insensitively(self):
        headers = self._captured(
            _request(forward_headers={"Host": "old.host", "Connection": "keep-alive"})
        )["headers"]
        assert "Host" not in headers
        assert "Connection" not in headers

    def test_sets_a_single_json_content_type_over_any_caller_value(self):
        headers = self._captured(_request(forward_headers={"Content-Type": "text/plain"}))[
            "headers"
        ]
        assert headers.get("Content-type") == "application/json"
