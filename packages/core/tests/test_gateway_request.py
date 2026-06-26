# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from generic_ml_cache_core.application.domain.model.gateway.gateway_request import GatewayRequest


def _make(model="claude-3-5-sonnet-20241022", messages=None, system=None, max_tokens=1024):
    return GatewayRequest(
        model=model,
        messages=messages or [{"role": "user", "content": "hi"}],
        system=system,
        max_tokens=max_tokens,
    )


class TestGenerateCacheKey:
    def test_returns_hex_string(self):
        key = _make().generate_cache_key()
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_same_input_same_key(self):
        r1 = _make(messages=[{"role": "user", "content": "hello"}])
        r2 = _make(messages=[{"role": "user", "content": "hello"}])
        assert r1.generate_cache_key() == r2.generate_cache_key()

    def test_different_message_different_key(self):
        r1 = _make(messages=[{"role": "user", "content": "a"}])
        r2 = _make(messages=[{"role": "user", "content": "b"}])
        assert r1.generate_cache_key() != r2.generate_cache_key()

    def test_max_tokens_excluded_from_key(self):
        r1 = _make(max_tokens=100)
        r2 = _make(max_tokens=9000)
        assert r1.generate_cache_key() == r2.generate_cache_key()

    def test_system_included_in_key(self):
        r1 = _make(system="be concise")
        r2 = _make(system=None)
        assert r1.generate_cache_key() != r2.generate_cache_key()


class TestSerializeRequest:
    def test_round_trips_to_json(self):
        req = _make(messages=[{"role": "user", "content": "test"}], max_tokens=512)
        body = json.loads(req.serialize_request())
        assert body["model"] == req.model
        assert body["messages"] == req.messages
        assert body["max_tokens"] == 512
        assert "system" not in body

    def test_system_included_when_set(self):
        req = _make(system="be brief")
        body = json.loads(req.serialize_request())
        assert body["system"] == "be brief"

    def test_returns_bytes(self):
        assert isinstance(_make().serialize_request(), bytes)


class TestProtocolMethods:
    def test_request_model(self):
        assert _make(model="claude-opus-4").request_model() == "claude-opus-4"

    def test_client_name(self):
        assert _make().client_name() == "anthropic"

    def test_is_cacheable(self):
        assert _make().is_cacheable() is True


class TestParseTokenUsage:
    def test_parses_usage_fields(self):
        body = json.dumps(
            {
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 5,
                    "cache_creation_input_tokens": 3,
                }
            }
        ).encode()
        usage = _make().parse_token_usage(body)
        assert usage is not None
        assert usage.input_tokens == 10
        assert usage.output_tokens == 20
        assert usage.cache_read_tokens == 5
        assert usage.cache_write_tokens == 3

    def test_returns_none_on_invalid_json(self):
        assert _make().parse_token_usage(b"not json") is None

    def test_returns_usage_with_nones_when_usage_missing(self):
        body = json.dumps({}).encode()
        usage = _make().parse_token_usage(body)
        assert usage is not None
        assert usage.input_tokens is None

    def test_returns_none_on_empty_bytes(self):
        assert _make().parse_token_usage(b"") is None
