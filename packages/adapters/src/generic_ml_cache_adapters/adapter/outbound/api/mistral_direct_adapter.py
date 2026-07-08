# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MistralDirectAdapter: calls Mistral's Chat Completions REST endpoint."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none
from generic_ml_cache_core.application.port.outbound.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.outbound.model_listing_port import ModelListingPort
from generic_ml_cache_core.common.errors import ConfigError

from generic_ml_cache_adapters.adapter.outbound.api._http import (
    request_json,
    translate_protocol_errors,
)

_BASE_URL = "https://api.mistral.ai/v1"


class MistralDirectAdapter(ApiClientPort, ModelListingPort):
    """Calls Mistral's Chat Completions API (OpenAI-compatible) using stdlib urllib.

    Auth: reads ``MISTRAL_API_KEY`` from the environment, or accepts ``api_key=`` at
    construction time. ``context`` and ``user_system_prompt`` map to a ``system``
    message; ``prompt`` maps to a ``user`` message. Usage comes from the standard
    ``prompt_tokens`` / ``completion_tokens`` block; Mistral reports no per-call cache
    count, reasoning split, or cost, so those stay ``None``.
    """

    name = "mistral"

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.api(
            "mistral", {ClientCapability.RUN, ClientCapability.LIST_MODELS}, "Mistral API"
        )

    def __init__(self, api_key: str | None = None, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def run(self, request: MlRequest) -> ClientRunResult:
        body = self._build_body(request)
        response = self._post("/chat/completions", body)
        with translate_protocol_errors("mistral", response):
            text = self._extract_text(response)
            usage = self._extract_usage(response)
        return ClientRunResult(exit_code=0, stdout=text, token_usage=usage)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_key_value(self) -> str:
        key = self._api_key or os.environ.get("MISTRAL_API_KEY", "")
        if not key:
            raise ConfigError(
                "MISTRAL_API_KEY is not set. Export it or pass api_key= to MistralDirectAdapter."
            )
        return key

    def _build_body(self, request: MlRequest) -> dict[str, Any]:
        system_parts: list[str] = []
        if request.context:
            system_parts.append(request.context)
        if request.user_system_prompt:
            system_parts.append(request.user_system_prompt)
        messages: list[dict[str, str]] = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": request.prompt})
        return {"model": request.model, "messages": messages}

    def list_models(self) -> list[ModelInfo]:
        """Return the models available to this account (``GET /v1/models``)."""
        data = self._get("/models")
        return [ModelInfo(id=m["id"], name=m["id"]) for m in data.get("data", []) if m.get("id")]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key_value()}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 (trusted provider endpoint, https)
            _BASE_URL + path,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        return request_json(req, provider="mistral", timeout=self._timeout)

    def _get(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(  # noqa: S310 (trusted provider endpoint, https)
            _BASE_URL + path,
            headers=self._headers(),
            method="GET",
        )
        return request_json(req, provider="mistral", timeout=self._timeout)

    def _extract_text(self, response: dict[str, Any]) -> str:
        # The answer is the first choice's message content (chat.completion shape).
        for choice in response.get("choices", []):
            message = choice.get("message", {})
            content = message.get("content", "")
            if isinstance(content, str) and content:
                return content if content.endswith("\n") else content + "\n"
        return "\n"

    def _extract_usage(self, response: dict[str, Any]) -> TokenUsage:
        usage_block: dict[str, Any] = response.get("usage", {})
        prompt_details: dict[str, Any] = usage_block.get("prompt_tokens_details") or {}
        return TokenUsage(
            input_tokens=int_or_none(usage_block.get("prompt_tokens")),
            output_tokens=int_or_none(usage_block.get("completion_tokens")),
            cache_read_tokens=int_or_none(prompt_details.get("cached_tokens")),
            cache_write_tokens=None,  # Mistral's prompt cache is read-only; no write count
            reasoning_tokens=None,  # no reasoning split in the usage block
            cost_usd=None,  # Mistral returns no dollar figure per call
            raw=dict(usage_block),
        )
