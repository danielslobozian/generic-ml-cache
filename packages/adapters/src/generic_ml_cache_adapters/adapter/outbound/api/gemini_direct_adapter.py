# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GeminiDirectAdapter: calls Google's Gemini generateContent REST endpoint."""

from __future__ import annotations

import json
import os
import urllib.error
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
from generic_ml_cache_core.common.errors import ConfigError, ProviderApiError

from generic_ml_cache_adapters.adapter.outbound.api._gemini_thinking import GeminiThinkingConfig

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiDirectAdapter(ApiClientPort, ModelListingPort):
    """Calls Google's Gemini generateContent REST API using stdlib urllib.

    Auth: reads GEMINI_API_KEY from the environment, or accepts api_key= at
    construction time. System-role messages map to systemInstruction; user and
    assistant messages map to contents entries with roles "user" and "model".
    ThoughtsTokenCount is captured as reasoning_tokens; cache_write_tokens and
    cost_usd are always None (Gemini does not report them per call).
    """

    name = "gemini"

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.api(
            "gemini", {ClientCapability.RUN, ClientCapability.LIST_MODELS}, "Google Gemini API"
        )

    def __init__(self, api_key: str | None = None, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def run(self, request: MlRequest) -> ClientRunResult:
        body = self._build_body(request)
        url = f"{_BASE_URL}/{request.model}:generateContent"
        response = self._post(url, body)
        text = self._extract_text(response)
        usage = self._extract_usage(response)
        return ClientRunResult(exit_code=0, stdout=text, token_usage=usage)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_key_value(self) -> str:
        key = self._api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ConfigError(
                "GEMINI_API_KEY is not set. Export it or pass api_key= to GeminiDirectAdapter."
            )
        return key

    def _build_body(self, request: MlRequest) -> dict[str, Any]:
        system_parts: list[dict[str, str]] = []
        if request.context:
            system_parts.append({"text": request.context})
        if request.user_system_prompt:
            system_parts.append({"text": request.user_system_prompt})
        contents = [{"role": "user", "parts": [{"text": request.prompt}]}]
        body: dict[str, Any] = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        if request.effort:
            config = GeminiThinkingConfig.from_effort(request.effort, request.model)
            body["generationConfig"] = {"thinkingConfig": config.to_dict()}
        return body

    def list_models(self) -> list[ModelInfo]:
        """Return all Gemini models that support generateContent."""
        data = self._get(_BASE_URL)
        models: list[ModelInfo] = []
        for m in data.get("models", []):
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            model_id = m.get("name", "").removeprefix("models/")
            if not model_id:
                continue
            display = m.get("displayName", model_id)
            models.append(ModelInfo(id=model_id, name=display))
        return models

    def _get(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(  # noqa: S310 (trusted provider endpoint, https)
            url,
            headers={"X-goog-api-key": self._api_key_value()},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 (trusted provider endpoint, https)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderApiError(
                provider="gemini", status_code=exc.code, body=error_body
            ) from exc

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 (trusted provider endpoint, https)
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": self._api_key_value(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 (trusted provider endpoint, https)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderApiError(
                provider="gemini", status_code=exc.code, body=error_body
            ) from exc

    def _extract_text(self, response: dict[str, Any]) -> str:
        candidates = response.get("candidates", [])
        if not candidates:
            return "\n"
        parts = candidates[0].get("content", {}).get("parts", [])
        # Collect only parts that carry text; thoughtSignature and other
        # non-text fields may appear alongside text in thinking-enabled models.
        text = "".join(p["text"] for p in parts if "text" in p)
        return text if text.endswith("\n") else text + "\n"

    def _extract_usage(self, response: dict[str, Any]) -> TokenUsage:
        meta = response.get("usageMetadata", {})
        return TokenUsage(
            input_tokens=int_or_none(meta.get("promptTokenCount")),
            output_tokens=int_or_none(meta.get("candidatesTokenCount")),
            cache_read_tokens=int_or_none(meta.get("cachedContentTokenCount")),
            cache_write_tokens=None,
            reasoning_tokens=int_or_none(meta.get("thoughtsTokenCount")),
            cost_usd=None,
            raw=dict(meta),
        )
