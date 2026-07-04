# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared API HTTP request + retry helper (G-1/V29)."""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from email.message import Message
from unittest.mock import MagicMock, patch

from generic_ml_cache_core.common.errors import ProviderApiError, ProviderProtocolError

from generic_ml_cache_adapters.adapter.outbound.api._http import RetryPolicy, request_json

_REQ = urllib.request.Request("https://provider.example/api")
_POLICY = RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=8.0)


def _ok(payload: bytes = b'{"ok": true}', status: int = 200) -> MagicMock:
    resp = MagicMock()
    entered = resp.__enter__.return_value
    entered.read.return_value = payload
    entered.status = status
    return resp


def _http_error(
    code: int, *, retry_after: int | None = None, body: bytes = b"err"
) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://x", code, "msg", headers, io.BytesIO(body))


def _call(side_effect, policy=_POLICY):
    sleeps: list[float] = []
    with patch(
        "generic_ml_cache_adapters.adapter.outbound.api._http.urllib.request.urlopen",
        side_effect=side_effect,
    ) as urlopen:
        try:
            result = request_json(
                _REQ, provider="acme", timeout=1.0, retry=policy, sleep=sleeps.append
            )
        except ProviderApiError as exc:
            return None, exc, sleeps, urlopen.call_count
        return result, None, sleeps, urlopen.call_count


def test_success_returns_parsed_json_without_retry():
    result, exc, sleeps, calls = _call([_ok(b'{"answer": 42}')])
    assert result == {"answer": 42}
    assert exc is None
    assert calls == 1
    assert sleeps == []


def test_malformed_json_body_raises_protocol_error_without_retry():
    result, exc, sleeps, calls = _call([_ok(b"this is not json")])
    assert result is None
    assert isinstance(exc, ProviderProtocolError)
    assert exc.status_code == 200
    assert calls == 1  # a bad payload will not fix itself — never retried
    assert sleeps == []


def test_non_object_json_body_raises_protocol_error():
    _, exc, _, calls = _call([_ok(b"[1, 2, 3]")])
    assert isinstance(exc, ProviderProtocolError)
    assert calls == 1


def test_non_utf8_body_raises_protocol_error():
    _, exc, _, calls = _call([_ok(b"\xff\xfe not utf-8")])
    assert isinstance(exc, ProviderProtocolError)
    assert calls == 1


def test_non_retryable_4xx_raises_immediately():
    result, exc, sleeps, calls = _call([_http_error(401, body=b"nope")])
    assert result is None
    assert exc is not None and exc.status_code == 401 and exc.provider == "acme"
    assert calls == 1  # 4xx (not 429) is never retried
    assert sleeps == []


def test_429_is_retried_then_succeeds():
    result, exc, sleeps, calls = _call([_http_error(429), _ok(b'{"ok": 1}')])
    assert result == {"ok": 1}
    assert calls == 2
    assert len(sleeps) == 1


def test_5xx_retried_up_to_max_attempts_then_raises():
    result, exc, sleeps, calls = _call([_http_error(503), _http_error(503), _http_error(503)])
    assert result is None
    assert exc is not None and exc.status_code == 503
    assert calls == 3  # max_attempts
    assert len(sleeps) == 2  # slept between the three attempts


def test_network_error_is_retried_then_translated_with_status_zero():
    err = urllib.error.URLError("connection refused")
    result, exc, sleeps, calls = _call([err, err, err])
    assert result is None
    assert exc is not None and exc.status_code == 0  # no HTTP response
    assert calls == 3
    assert len(sleeps) == 2


def test_retry_after_header_is_honoured():
    _result, _exc, sleeps, _calls = _call([_http_error(429, retry_after=2), _ok()])
    assert sleeps == [2.0]  # slept exactly the server's Retry-After, not jittered backoff


def test_max_attempts_one_means_no_retry():
    result, exc, sleeps, calls = _call([_http_error(500)], policy=RetryPolicy(max_attempts=1))
    assert result is None and exc is not None and exc.status_code == 500
    assert calls == 1
    assert sleeps == []
