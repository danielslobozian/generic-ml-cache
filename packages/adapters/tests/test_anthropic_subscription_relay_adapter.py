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


def _ok_response(body: bytes, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)
    response.status = status
    response.read.return_value = body
    return response


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
