# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AnthropicDirectAdapter — no network calls; all HTTP is patched."""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort

from generic_ml_cache_adapters.adapter.out.api.anthropic_direct_adapter import (
    AnthropicDirectAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Realistic response from the Anthropic Messages API.
_FIXTURE_RESPONSE: dict[str, Any] = {
    "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
    "type": "message",
    "role": "assistant",
    "content": [
        {
            "type": "text",
            "text": "AI analyzes vast data, finds patterns, and makes predictions.",
        }
    ],
    "model": "claude-sonnet-4-6",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 8,
        "output_tokens": 20,
    },
}

# Response that includes cache token counts.
_FIXTURE_CACHED_RESPONSE: dict[str, Any] = {
    "id": "msg_02",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "Cached reply."}],
    "model": "claude-sonnet-4-6",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_input_tokens": 80,
        "cache_creation_input_tokens": 20,
    },
}


def _adapter(api_key: str = "test-key") -> AnthropicDirectAdapter:
    return AnthropicDirectAdapter(api_key=api_key)


def _patch_post(adapter: AnthropicDirectAdapter, response: dict[str, Any]):
    adapter._post = lambda path, body: response  # type: ignore[assignment]


def _request(
    prompt: str = "hi",
    context: str = "",
    model: str = "claude-sonnet-4-6",
    effort: str = "",
    user_system_prompt=None,
) -> MlRequest:
    return MlRequest(
        model=model,
        effort=effort,
        context=context,
        prompt=prompt,
        user_system_prompt=user_system_prompt,
    )


# ---------------------------------------------------------------------------
# Port contract
# ---------------------------------------------------------------------------


def test_is_an_api_client_port():
    assert isinstance(_adapter(), ApiClientPort)


# ---------------------------------------------------------------------------
# Body building
# ---------------------------------------------------------------------------


def test_prompt_maps_to_user_message():
    body = _adapter()._build_body(_request(prompt="hello"))
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_context_becomes_system_field():
    body = _adapter()._build_body(_request(context="be terse", prompt="hi"))
    assert body["system"] == "be terse"
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"


def test_empty_context_omits_system_field():
    body = _adapter()._build_body(_request(context="", prompt="hi"))
    assert "system" not in body


def test_context_and_system_prompt_joined_with_double_newline():
    body = _adapter()._build_body(
        _request(context="be terse", prompt="go", user_system_prompt="be helpful")
    )
    assert body["system"] == "be terse\n\nbe helpful"
    assert len(body["messages"]) == 1


def test_none_user_system_prompt_excluded_from_system():
    body = _adapter()._build_body(_request(context="ctx", prompt="hi", user_system_prompt=None))
    assert body["system"] == "ctx"


def test_max_tokens_present_in_body():
    body = _adapter()._build_body(_request())
    assert "max_tokens" in body
    assert body["max_tokens"] == AnthropicDirectAdapter._DEFAULT_MAX_TOKENS


def test_max_tokens_override_at_construction():
    adapter = AnthropicDirectAdapter(api_key="k", max_tokens=4096)
    body = adapter._build_body(_request())
    assert body["max_tokens"] == 4096


def test_model_present_in_body():
    body = _adapter()._build_body(_request(model="claude-haiku-4-5"))
    assert body["model"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_fixture_response():
    text = _adapter()._extract_text(_FIXTURE_RESPONSE)
    assert "AI analyzes" in text


def test_extract_text_ensures_trailing_newline():
    response = {"content": [{"type": "text", "text": "no newline"}]}
    assert _adapter()._extract_text(response).endswith("\n")


def test_extract_text_does_not_double_newline():
    response = {"content": [{"type": "text", "text": "already\n"}]}
    assert _adapter()._extract_text(response) == "already\n"


def test_extract_text_empty_content_returns_newline():
    assert _adapter()._extract_text({"content": []}) == "\n"


def test_extract_text_skips_thinking_blocks():
    response = {
        "content": [
            {"type": "thinking", "thinking": "Let me reason..."},
            {"type": "text", "text": "final answer"},
        ]
    }
    assert _adapter()._extract_text(response) == "final answer\n"


def test_extract_text_concatenates_multiple_text_blocks():
    response = {
        "content": [
            {"type": "text", "text": "part one "},
            {"type": "text", "text": "part two"},
        ]
    }
    assert "part one part two" in _adapter()._extract_text(response)


# ---------------------------------------------------------------------------
# Usage extraction
# ---------------------------------------------------------------------------


def test_usage_maps_input_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.input_tokens == 8


def test_usage_maps_output_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.output_tokens == 20


def test_usage_reasoning_tokens_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.reasoning_tokens is None


def test_usage_cost_usd_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cost_usd is None


def test_usage_cache_read_tokens_from_cache_read_input_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.cache_read_tokens == 80


def test_usage_cache_write_tokens_from_cache_creation_input_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.cache_write_tokens == 20


def test_usage_absent_cache_fields_are_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cache_read_tokens is None
    assert usage.cache_write_tokens is None


def test_usage_raw_preserves_full_usage_block():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.raw["input_tokens"] == 8
    assert usage.raw["output_tokens"] == 20


def test_usage_missing_usage_block_returns_all_none():
    usage = _adapter()._extract_usage({})
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.raw == {}


# ---------------------------------------------------------------------------
# run() integration (patching _post)
# ---------------------------------------------------------------------------


def test_run_returns_client_run_result_with_text():
    adapter = _adapter()
    _patch_post(adapter, _FIXTURE_RESPONSE)
    result = adapter.run(_request())
    assert result.exit_code == 0
    assert "AI analyzes" in result.stdout


def test_run_token_usage_flows_through():
    adapter = _adapter()
    _patch_post(adapter, _FIXTURE_RESPONSE)
    result = adapter.run(_request())
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == 8
    assert result.token_usage.reasoning_tokens is None


def test_run_files_is_empty():
    adapter = _adapter()
    _patch_post(adapter, _FIXTURE_RESPONSE)
    result = adapter.run(_request())
    assert result.files == ()


def test_run_sends_correct_model():
    adapter = _adapter()
    captured = {}

    def fake_post(path, body):
        captured["body"] = body
        return _FIXTURE_RESPONSE

    adapter._post = fake_post  # type: ignore[assignment]
    adapter.run(_request(model="claude-haiku-4-5"))
    assert captured["body"]["model"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Auth / HTTP error handling
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = AnthropicDirectAdapter()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        adapter.run(_request())


def test_api_key_from_env_is_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    adapter = AnthropicDirectAdapter()
    assert adapter._api_key_value() == "env-key"


def test_explicit_api_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    adapter = AnthropicDirectAdapter(api_key="explicit-key")
    assert adapter._api_key_value() == "explicit-key"


def test_http_error_raises_runtime_error_with_status(monkeypatch):
    error_body = b'{"error": {"type": "authentication_error", "message": "invalid api key"}}'
    http_error = urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/messages",
        code=401,
        msg="Unauthorized",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        adapter = _adapter()
        with pytest.raises(RuntimeError, match="401"):
            adapter.run(_request())


# ---------------------------------------------------------------------------
# list_models()
# ---------------------------------------------------------------------------

_MODELS_RESPONSE = {
    "data": [
        {"id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "type": "model"},
        {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6", "type": "model"},
        {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5", "type": "model"},
    ],
    "has_more": False,
    "first_id": "claude-opus-4-8",
    "last_id": "claude-haiku-4-5",
}


def test_list_models_returns_all_language_models():
    adapter = _adapter()
    adapter._get = lambda path: _MODELS_RESPONSE  # type: ignore[assignment]
    models = adapter.list_models()
    ids = [m.id for m in models]
    assert "claude-opus-4-8" in ids
    assert "claude-sonnet-4-6" in ids
    assert "claude-haiku-4-5" in ids


def test_list_models_uses_display_name():
    adapter = _adapter()
    adapter._get = lambda path: _MODELS_RESPONSE  # type: ignore[assignment]
    by_id = {m.id: m for m in adapter.list_models()}
    assert by_id["claude-opus-4-8"].name == "Claude Opus 4.8"


def test_list_models_filters_out_non_model_types():
    response = {
        "data": [
            {"id": "claude-sonnet-4-6", "display_name": "Sonnet", "type": "model"},
            {"id": "something-else", "display_name": "Other", "type": "other"},
        ]
    }
    adapter = _adapter()
    adapter._get = lambda path: response  # type: ignore[assignment]
    ids = [m.id for m in adapter.list_models()]
    assert "claude-sonnet-4-6" in ids
    assert "something-else" not in ids


def test_list_models_empty_data_returns_empty_list():
    adapter = _adapter()
    adapter._get = lambda path: {"data": []}  # type: ignore[assignment]
    assert adapter.list_models() == []


def test_list_models_http_error_raises_runtime_error():
    error_body = b'{"error": {"type": "authentication_error", "message": "invalid api key"}}'
    http_error = urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/models",
        code=401,
        msg="Unauthorized",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(RuntimeError, match="401"):
            _adapter().list_models()
