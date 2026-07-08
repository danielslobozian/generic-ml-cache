# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for MistralDirectAdapter — no network calls; all HTTP is stubbed."""

from __future__ import annotations

from typing import Any

import pytest
from generic_ml_cache_bootstrap.discovery.composition import registered_names
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.outbound.api_client_port import ApiClientPort
from generic_ml_cache_core.common.errors import ConfigError

from generic_ml_cache_adapters.adapter.outbound.api.mistral_direct_adapter import (
    MistralDirectAdapter,
)

# A realistic Mistral chat.completion response.
_FIXTURE_RESPONSE: dict[str, Any] = {
    "id": "cmpl-abc",
    "object": "chat.completion",
    "model": "mistral-medium-3.5",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "AI finds patterns."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 8, "completion_tokens": 20, "total_tokens": 28},
}


def _adapter(api_key: str = "test-key") -> MistralDirectAdapter:
    return MistralDirectAdapter(api_key=api_key)


def _patch_post(adapter: MistralDirectAdapter, response: dict[str, Any]) -> None:
    adapter._post = lambda path, body: response  # type: ignore[assignment]


def _patch_get(adapter: MistralDirectAdapter, response: dict[str, Any]) -> None:
    adapter._get = lambda path: response  # type: ignore[assignment]


def _request(
    prompt: str = "hi",
    context: str = "",
    model: str = "mistral-medium-3.5",
    effort: str = "",
    user_system_prompt: str | None = None,
) -> MlRequest:
    return MlRequest(
        model=model,
        effort=effort,
        context=context,
        prompt=prompt,
        user_system_prompt=user_system_prompt,
    )


class TestContract:
    def test_is_an_api_client_port(self):
        assert isinstance(_adapter(), ApiClientPort)

    def test_descriptor(self):
        d = MistralDirectAdapter.descriptor()
        assert d.client_name == "mistral"
        assert ClientCapability.RUN in d.capabilities
        assert ClientCapability.LIST_MODELS in d.capabilities

    def test_registered_via_entry_point(self):
        assert "mistral" in registered_names()


class TestBodyBuilding:
    def test_prompt_maps_to_user_message(self):
        body = _adapter()._build_body(_request(prompt="hello"))
        assert body["messages"][-1] == {"role": "user", "content": "hello"}
        assert body["model"] == "mistral-medium-3.5"

    def test_context_becomes_system_message(self):
        body = _adapter()._build_body(_request(context="be terse", prompt="hi"))
        assert body["messages"][0] == {"role": "system", "content": "be terse"}
        assert body["messages"][-1]["role"] == "user"

    def test_empty_context_omits_system_message(self):
        body = _adapter()._build_body(_request(context="", prompt="hi"))
        assert all(m["role"] != "system" for m in body["messages"])

    def test_context_and_system_prompt_joined_with_double_newline(self):
        body = _adapter()._build_body(
            _request(context="be terse", prompt="go", user_system_prompt="be helpful")
        )
        assert body["messages"][0]["content"] == "be terse\n\nbe helpful"


class TestRun:
    def test_returns_text_and_usage(self):
        adapter = _adapter()
        _patch_post(adapter, _FIXTURE_RESPONSE)
        result = adapter.run(_request())
        assert result.exit_code == 0
        assert result.stdout == "AI finds patterns.\n"  # trailing newline normalised
        assert result.token_usage is not None
        assert result.token_usage.input_tokens == 8  # prompt_tokens
        assert result.token_usage.output_tokens == 20  # completion_tokens
        assert result.token_usage.cache_read_tokens is None
        assert result.token_usage.reasoning_tokens is None
        assert result.token_usage.cost_usd is None

    def test_empty_choices_yields_newline(self):
        adapter = _adapter()
        _patch_post(adapter, {"choices": [], "usage": {}})
        assert adapter.run(_request()).stdout == "\n"

    def test_cached_tokens_map_to_cache_read(self):
        # Mistral reports prompt_tokens_details.cached_tokens (verified live).
        adapter = _adapter()
        response = dict(_FIXTURE_RESPONSE)
        response["usage"] = {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 80},
        }
        _patch_post(adapter, response)
        usage = adapter.run(_request()).token_usage
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.cache_read_tokens == 80


class TestModelListing:
    def test_list_models(self):
        adapter = _adapter()
        _patch_get(adapter, {"data": [{"id": "mistral-medium-3.5"}, {"id": "codestral-latest"}]})
        models = adapter.list_models()
        assert [m.id for m in models] == ["mistral-medium-3.5", "codestral-latest"]

    def test_list_models_skips_entries_without_id(self):
        adapter = _adapter()
        _patch_get(adapter, {"data": [{"id": "ok"}, {"name": "no-id"}]})
        assert [m.id for m in adapter.list_models()] == ["ok"]


class TestAuth:
    def test_missing_key_raises_config_error(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        with pytest.raises(ConfigError):
            MistralDirectAdapter()._api_key_value()

    def test_key_from_env(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "env-key")
        assert MistralDirectAdapter()._api_key_value() == "env-key"
