# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for GeminiDirectAdapter — no network calls; all HTTP is patched."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from generic_ml_cache_core.adapter.out.api.gemini_direct_adapter import GeminiDirectAdapter
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Mirrors the actual curl response from the real API (gemini-3.5-flash).
# The part has both "text" and "thoughtSignature" — the adapter must take
# only the text and ignore thoughtSignature.
_FIXTURE_RESPONSE: Dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": "AI analyzes vast data, finds patterns, and makes predictions.",
                        "thoughtSignature": "EqYLCqMLAQw51seqAYDTC8W7...",
                    }
                ],
                "role": "model",
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 8,
        "candidatesTokenCount": 20,
        "totalTokenCount": 395,
        "thoughtsTokenCount": 367,
        "serviceTier": "standard",
    },
    "modelVersion": "gemini-3.5-flash",
}

# Response that includes cachedContentTokenCount (cache hit scenario).
_FIXTURE_CACHED_RESPONSE: Dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "Cached reply."}],
                "role": "model",
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 100,
        "candidatesTokenCount": 10,
        "cachedContentTokenCount": 80,
        "thoughtsTokenCount": 0,
        "totalTokenCount": 110,
    },
}


def _adapter(api_key: str = "test-key") -> GeminiDirectAdapter:
    return GeminiDirectAdapter(api_key=api_key)


def _patch_post(adapter: GeminiDirectAdapter, response: Dict[str, Any]):
    """Monkeypatch _post to return a fixture without touching the network."""
    adapter._post = lambda url, body: response  # type: ignore[assignment]


def _request(
    prompt: str = "hi",
    context: str = "",
    model: str = "gemini-3.5-flash",
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


def test_prompt_maps_to_user_content():
    body = _adapter()._build_body(_request(prompt="hello"))
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]


def test_context_becomes_system_instruction():
    body = _adapter()._build_body(_request(context="be terse", prompt="hi"))
    assert "systemInstruction" in body
    assert body["systemInstruction"] == {"parts": [{"text": "be terse"}]}
    assert len(body["contents"]) == 1
    assert body["contents"][0]["role"] == "user"


def test_empty_context_omits_system_instruction():
    body = _adapter()._build_body(_request(context="", prompt="hi"))
    assert "systemInstruction" not in body


def test_context_and_system_prompt_both_become_system_instruction():
    body = _adapter()._build_body(
        _request(context="be terse", prompt="go", user_system_prompt="be helpful")
    )
    parts = body["systemInstruction"]["parts"]
    assert len(parts) == 2
    assert parts[0]["text"] == "be terse"
    assert parts[1]["text"] == "be helpful"
    assert len(body["contents"]) == 1


def test_none_user_system_prompt_omits_from_system_instruction():
    body = _adapter()._build_body(_request(context="ctx", prompt="hi", user_system_prompt=None))
    assert body["systemInstruction"] == {"parts": [{"text": "ctx"}]}


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_fixture_response():
    text = _adapter()._extract_text(_FIXTURE_RESPONSE)
    assert "AI analyzes" in text


def test_extract_text_ignores_thought_signature():
    # Part has both text and thoughtSignature — only text is taken.
    text = _adapter()._extract_text(_FIXTURE_RESPONSE)
    assert "thoughtSignature" not in text
    assert "EqYL" not in text


def test_extract_text_ensures_trailing_newline():
    response = {
        "candidates": [
            {"content": {"parts": [{"text": "no newline"}], "role": "model"}}
        ]
    }
    assert _adapter()._extract_text(response).endswith("\n")


def test_extract_text_does_not_double_newline():
    response = {
        "candidates": [
            {"content": {"parts": [{"text": "already\n"}], "role": "model"}}
        ]
    }
    text = _adapter()._extract_text(response)
    assert text == "already\n"


def test_extract_text_empty_candidates_returns_newline():
    assert _adapter()._extract_text({"candidates": []}) == "\n"


def test_extract_text_skips_parts_without_text_key():
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thoughtSignature": "abc"},  # no text key
                        {"text": "real answer"},
                    ],
                    "role": "model",
                }
            }
        ]
    }
    assert _adapter()._extract_text(response) == "real answer\n"


def test_extract_text_concatenates_multiple_text_parts():
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "part one "}, {"text": "part two"}],
                    "role": "model",
                }
            }
        ]
    }
    assert "part one part two" in _adapter()._extract_text(response)


# ---------------------------------------------------------------------------
# Usage extraction
# ---------------------------------------------------------------------------


def test_usage_maps_prompt_token_count():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.input_tokens == 8


def test_usage_maps_candidates_token_count():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.output_tokens == 20


def test_usage_maps_thoughts_token_count_as_reasoning():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.reasoning_tokens == 367


def test_usage_cache_write_tokens_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cache_write_tokens is None


def test_usage_cost_usd_always_none():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cost_usd is None


def test_usage_cached_content_token_count_maps_to_cache_read():
    usage = _adapter()._extract_usage(_FIXTURE_CACHED_RESPONSE)
    assert usage.cache_read_tokens == 80


def test_usage_absent_cached_content_is_none():
    # Base fixture has no cachedContentTokenCount — must be None, not 0.
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.cache_read_tokens is None


def test_usage_raw_preserves_full_metadata_block():
    usage = _adapter()._extract_usage(_FIXTURE_RESPONSE)
    assert usage.raw["promptTokenCount"] == 8
    assert usage.raw["thoughtsTokenCount"] == 367


def test_usage_absent_thoughts_token_count_is_none():
    response = {
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}
    }
    usage = _adapter()._extract_usage(response)
    assert usage.reasoning_tokens is None


def test_usage_missing_usage_metadata_returns_all_none():
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
    assert result.token_usage.reasoning_tokens == 367


def test_run_files_is_empty():
    adapter = _adapter()
    _patch_post(adapter, _FIXTURE_RESPONSE)
    result = adapter.run(_request())
    assert result.files == []


# ---------------------------------------------------------------------------
# Effort → thinkingConfig
# ---------------------------------------------------------------------------


def test_effort_set_adds_generation_config():
    body = _adapter()._build_body(_request(effort="high"))
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "high"


def test_effort_low_maps_correctly():
    body = _adapter()._build_body(_request(effort="low"))
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


def test_effort_medium_maps_correctly():
    body = _adapter()._build_body(_request(effort="medium"))
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "medium"


def test_empty_effort_omits_generation_config():
    body = _adapter()._build_body(_request(effort=""))
    assert "generationConfig" not in body


def test_run_passes_effort_to_body():
    adapter = _adapter()
    captured = {}

    def fake_post(url, body):
        captured["body"] = body
        return _FIXTURE_RESPONSE

    adapter._post = fake_post  # type: ignore[assignment]
    adapter.run(_request(effort="high"))
    assert captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "high"


# ---------------------------------------------------------------------------
# Auth / HTTP error handling
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    adapter = GeminiDirectAdapter()  # no api_key=
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        adapter.run(_request())


def test_api_key_from_env_is_used(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    adapter = GeminiDirectAdapter()
    assert adapter._api_key_value() == "env-key"


def test_explicit_api_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    adapter = GeminiDirectAdapter(api_key="explicit-key")
    assert adapter._api_key_value() == "explicit-key"


def test_http_error_raises_runtime_error_with_status(monkeypatch):
    error_body = b'{"error": {"code": 403, "message": "API key invalid"}}'
    http_error = urllib.error.HTTPError(
        url="https://example.com",
        code=403,
        msg="Forbidden",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        adapter = _adapter()
        with pytest.raises(RuntimeError, match="403"):
            adapter.run(_request())


# ---------------------------------------------------------------------------
# list_models()
# ---------------------------------------------------------------------------

_MODELS_RESPONSE: Dict[str, Any] = {
    "models": [
        {
            "name": "models/gemini-2.5-flash",
            "displayName": "Gemini 2.5 Flash",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {
            "name": "models/gemini-3.5-flash",
            "displayName": "Gemini 3.5 Flash",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {
            "name": "models/text-embedding-004",
            "displayName": "Text Embedding 004",
            "supportedGenerationMethods": ["embedContent"],
        },
        {
            "name": "models/gemini-2.5-flash-tts",
            "displayName": "Gemini 2.5 Flash TTS",
            "supportedGenerationMethods": ["generateContent"],
        },
    ]
}


def test_list_models_filters_to_generate_content_only():
    adapter = _adapter()
    adapter._get = lambda url: _MODELS_RESPONSE
    models = adapter.list_models()
    ids = [m.id for m in models]
    assert "text-embedding-004" not in ids
    assert "gemini-2.5-flash" in ids
    assert "gemini-3.5-flash" in ids
    assert "gemini-2.5-flash-tts" in ids


def test_list_models_strips_models_prefix():
    adapter = _adapter()
    adapter._get = lambda url: _MODELS_RESPONSE
    models = adapter.list_models()
    assert all(not m.id.startswith("models/") for m in models)


def test_list_models_uses_display_name():
    adapter = _adapter()
    adapter._get = lambda url: _MODELS_RESPONSE
    by_id = {m.id: m for m in adapter.list_models()}
    assert by_id["gemini-2.5-flash"].name == "Gemini 2.5 Flash"
    assert by_id["gemini-3.5-flash"].name == "Gemini 3.5 Flash"


def test_list_models_empty_response_returns_empty_list():
    adapter = _adapter()
    adapter._get = lambda url: {"models": []}
    assert adapter.list_models() == []


def test_list_models_http_error_raises_runtime_error():
    import io
    error_body = b'{"error": {"code": 401, "message": "Unauthorized"}}'
    http_error = urllib.error.HTTPError(
        url="https://example.com", code=401, msg="Unauthorized",
        hdrs=MagicMock(), fp=io.BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(RuntimeError, match="401"):
            _adapter().list_models()
