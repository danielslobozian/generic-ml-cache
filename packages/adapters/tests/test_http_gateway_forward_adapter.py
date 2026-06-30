# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

from generic_ml_cache_core.application.domain.model.gateway.gateway_request import GatewayRequest

from generic_ml_cache_adapters.adapter.out.gateway.http_gateway_forward_adapter import (
    HttpGatewayForwardAdapter,
)


def _make_request():
    return GatewayRequest(
        body={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 1024,
        }
    )


_RESPONSE_BODY = b'{"content":[{"text":"ok"}]}'


class TestForward:
    def test_returns_200_on_success(self):
        adapter = HttpGatewayForwardAdapter()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = _RESPONSE_BODY

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = adapter.forward(_make_request(), "sk-test", "https://example.com", {})

        assert result.status_code == 200
        assert result.body_bytes == _RESPONSE_BODY

    def test_captures_http_error(self):
        adapter = HttpGatewayForwardAdapter()
        error_body = b'{"error":"rate_limited"}'
        http_err = urllib.error.HTTPError(
            url="https://example.com",
            code=429,
            msg="Too Many Requests",
            hdrs=MagicMock(),
            fp=BytesIO(error_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            result = adapter.forward(_make_request(), "sk-test", "https://example.com", {})

        assert result.status_code == 429
        assert result.body_bytes == error_body


class TestBuildHeaders:
    def _forward_headers(self, **headers):
        adapter = HttpGatewayForwardAdapter()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"{}"
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return mock_response

        with patch("urllib.request.urlopen", fake_urlopen):
            adapter.forward(_make_request(), "sk-test", "https://example.com", headers)
        return captured["headers"]

    def test_sets_content_type(self):
        hdrs = self._forward_headers()
        assert hdrs.get("Content-type") == "application/json"

    def test_strips_hop_by_hop_headers(self):
        hdrs = self._forward_headers(host="old.host", connection="keep-alive")
        assert "Host" not in hdrs
        assert "Connection" not in hdrs

    def test_uses_api_token_as_x_api_key_when_no_auth(self):
        hdrs = self._forward_headers()
        assert hdrs.get("X-api-key") == "sk-test"

    def test_does_not_override_existing_authorization(self):
        hdrs = self._forward_headers(authorization="Bearer existing")
        assert "X-api-key" not in hdrs
        assert hdrs.get("Authorization") == "Bearer existing"
