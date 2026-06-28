# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAIDirectAdapter — no network calls; all HTTP is patched.

The fixture response is derived from a real Responses API call
(gpt-4.1-mini-2025-04-14, prompt "Reply with only: ok").
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from generic_ml_cache_adapters.adapter.out.api.openai_direct_adapter import OpenAIDirectAdapter
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort

# ---------------------------------------------------------------------------
# Fixtures — derived from a real Responses API call
# ---------------------------------------------------------------------------

_FIXTURE_RESPONSE: Dict[str, Any] = {
    "id": "resp_0f440ab3bd3a8c88006a3c3f3d975481",
    "object": "response",
    "model": "gpt-4.1-mini-2025-04-14",
    "status": "completed",
    "output": [
        {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "AI analyzes vast data, finds patterns, and makes predictions.",
                    "annotations": [],
                    "logprobs": [],
                }
            ],
        }
    ],
    "usage": {
        "input_tokens": 12,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 20,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 32,
    },
}

# Response that includes non-zero cache and reasoning counts.
_FIXTURE_CACHED_RESPONSE: Dict[str, Any] = {
    "id": "resp_02",
    "object": "response",
    "model": "gpt-4.1-mini-2025-04-14",
    "status": "completed",
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "Cached reply."}],
        }
    ],
    "usage": {
        "input_tokens": 1200,
        "input_tokens_details": {"cached_tokens": 1024},
        "output_tokens": 30,
        "output_tokens_details": {"reasoning_tokens": 15},
        "total_tokens": 1230,
    },
}


def _adapter(api_key: str = "test-key") -> OpenAIDirectAdapter:
    return OpenAIDirectAdapter(api_key=api_key)


def _patch_post(adapter: OpenAIDirectAdapter, response: Dict[str, Any]):
    adapter._post = lambda path, body: response  # type: ignore[assignment]


def _request(
    prompt: str = "hi",
    context: str = "",
    model: str = "gpt-4.1-mini",
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


def test_prompt_maps_to_user_input_message():
    body = _adapter()._build_body(_request(prompt="hello"))
    assert body["input"] == [{"role": "user", "content": "hello"}]


def test_context_becomes_instructions_field():
    body = _adapter()._build_body(_request(context="be terse", prompt="hi"))
    assert body["instructions"] == "be terse"
    assert len(body["input"]) == 1
    assert body["input"][0]["role"] == "user"


def test_empty_context_omits_instructions():
    body = _adapter()._build_body(_request(context="", prompt="hi"))
    assert "instructions" not in body


def test_context_and_system_prompt_joined_with_double_newline():
    body = _adapter()._build_body(
        _request(context="be terse", prompt="go", user_system_prompt="be helpful")
    )
    assert body["instructions"] == "be terse\n\nbe helpful"
    assert len(body["input"]) == 1


def test_none_user_system_prompt_excluded_from_instructions():
    body = _adapter()._build_body(_request(context="ctx", prompt="hi", user_system_prompt=None))
    assert body["instructions"] == "ctx"


def test_model_present_in_body():
    body = _adapter()._build_body(_request(model="gpt-4.1"))
    assert body["model"] == "gpt-4.1"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_fixture_response():
    text = _adapter()._extract_text(_FIXTURE_RESPONSE)
    assert "AI analyzes" in text


def test_extract_text_ensures_trailing_newline():
    response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "no newline"}],
            }
        ]
    }
    assert _adapter()._extract_text(response).endswith("\n")


def test_extract_text_does_not_double_newline():
    response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "already\n"}],
            }
        ]
    }
    assert _adapter()._extract_text(response) == "already\n"


def test_extract_text_empty_output_returns_newline():
    assert _adapter()._extract_text({"output": []}) == "\n"


def test_extract_text_skips_non_output_text_content():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "refusal", "refusal": "I cannot do that."},
                    {"type": "output_text", "text": "actual reply"},
                ],
            }
        ]
    }
    assert _adapter()._extract_text(response) == "actual reply\n"


def test_extract_text_skips_non_message_output_items():
    response = {
        "output": [
            {"type": "reasoning", "content": "thinking..."},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "answer"}],
            },
        ]
    }
    assert _adapter()._extract_text(response) == "answer\n"


def test_extract_text_concatenates_multiple_output_text_parts():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "part one "},
                    {"type": "output_text", "text": "part two"},
                ],
            }
        ]
    }
    assert "part one part two" in _adapter()._extract_text(response)


# ---------------------------------------------------------------------------
# Usage extraction
# ---------------------------------------------------------------------------


def test_usage_maps_input_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.input_tokens == 12


def test_usage_maps_output_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.output_tokens == 20


def test_usage_cache_read_from_input_tokens_details_cached_tokens():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.cache_read_tokens == 1024


def test_usage_cache_write_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.cache_write_tokens is None


def test_usage_reasoning_from_output_tokens_details():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.reasoning_tokens == 15


def test_usage_cost_usd_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cost_usd is None


def test_usage_zero_reasoning_tokens_is_zero_not_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    # Fixture has reasoning_tokens: 0 — zero is a reported value, not unknown
    assert usage.reasoning_tokens == 0


def test_usage_absent_details_returns_none_for_nested_fields():
    usage = _adapter()._extract_usage({"usage": {"input_tokens": 5, "output_tokens": 3}})
    assert usage.cache_read_tokens is None
    assert usage.reasoning_tokens is None


def test_usage_raw_preserves_full_usage_block():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.raw["input_tokens"] == 12
    assert "input_tokens_details" in usage.raw


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
    assert result.token_usage.input_tokens == 12


def test_run_files_is_empty():
    adapter = _adapter()
    _patch_post(adapter, _FIXTURE_RESPONSE)
    result = adapter.run(_request())
    assert result.files == []


def test_run_sends_correct_model():
    adapter = _adapter()
    captured = {}

    def fake_post(path, body):
        captured["body"] = body
        return _FIXTURE_RESPONSE

    adapter._post = fake_post  # type: ignore[assignment]
    adapter.run(_request(model="gpt-4.1"))
    assert captured["body"]["model"] == "gpt-4.1"


def test_run_posts_to_responses_endpoint():
    adapter = _adapter()
    captured = {}

    def fake_post(path, body):
        captured["path"] = path
        return _FIXTURE_RESPONSE

    adapter._post = fake_post  # type: ignore[assignment]
    adapter.run(_request())
    assert captured["path"] == "/responses"


# ---------------------------------------------------------------------------
# Auth / HTTP error handling
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIDirectAdapter()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        adapter.run(_request())


def test_api_key_from_env_is_used(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    adapter = OpenAIDirectAdapter()
    assert adapter._api_key_value() == "env-key"


def test_explicit_api_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    adapter = OpenAIDirectAdapter(api_key="explicit-key")
    assert adapter._api_key_value() == "explicit-key"


def test_http_error_raises_runtime_error_with_status(monkeypatch):
    error_body = b'{"error": {"message": "invalid api key", "type": "invalid_request_error"}}'
    http_error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/responses",
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

_MODELS_RESPONSE: Dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "gpt-4.1", "object": "model", "created": 1744143600, "owned_by": "openai"},
        {"id": "gpt-4.1-mini", "object": "model", "created": 1744144600, "owned_by": "openai"},
        {"id": "o3", "object": "model", "created": 1744145600, "owned_by": "openai"},
        {
            "id": "ft:gpt-4o:acme:custom-1",
            "object": "model",
            "created": 1700000000,
            "owned_by": "acme-org",
        },
    ],
}


def test_list_models_returns_openai_owned_models():
    adapter = _adapter()
    adapter._get = lambda path: _MODELS_RESPONSE  # type: ignore[assignment]
    ids = [m.id for m in adapter.list_models()]
    assert "gpt-4.1" in ids
    assert "gpt-4.1-mini" in ids
    assert "o3" in ids


def test_list_models_excludes_fine_tuned_models():
    adapter = _adapter()
    adapter._get = lambda path: _MODELS_RESPONSE  # type: ignore[assignment]
    ids = [m.id for m in adapter.list_models()]
    assert "ft:gpt-4o:acme:custom-1" not in ids


def test_list_models_uses_id_as_name():
    adapter = _adapter()
    adapter._get = lambda path: _MODELS_RESPONSE  # type: ignore[assignment]
    by_id = {m.id: m for m in adapter.list_models()}
    assert by_id["gpt-4.1"].name == "gpt-4.1"


def test_list_models_empty_data_returns_empty_list():
    adapter = _adapter()
    adapter._get = lambda path: {"data": []}  # type: ignore[assignment]
    assert adapter.list_models() == []


def test_list_models_http_error_raises_runtime_error():
    error_body = b'{"error": {"message": "invalid api key"}}'
    http_error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/models",
        code=401,
        msg="Unauthorized",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(RuntimeError, match="401"):
            _adapter().list_models()
