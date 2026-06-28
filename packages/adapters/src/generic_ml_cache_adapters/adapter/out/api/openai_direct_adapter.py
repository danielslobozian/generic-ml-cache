# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""OpenAIDirectAdapter: calls OpenAI's Responses REST endpoint."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from generic_ml_cache_core.adapter.registry import adapter
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.model_listing_port import ModelListingPort

_BASE_URL = "https://api.openai.com/v1"


@adapter
class OpenAIDirectAdapter(ApiClientPort, ModelListingPort):
    """Calls OpenAI's Responses API using stdlib urllib.

    Auth: reads OPENAI_API_KEY from the environment, or accepts api_key= at
    construction time. context and user_system_prompt map to the 'instructions'
    field; prompt maps to a user input message.

    Caching is automatic (prompts ≥1024 tokens) and read-only, so
    cache_write_tokens is always None. reasoning_tokens comes from
    output_tokens_details.reasoning_tokens. cost_usd is always None.
    """

    name = "openai"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def run(self, request: MlRequest) -> ClientRunResult:
        body = self._build_body(request)
        response = self._post("/responses", body)
        text = self._extract_text(response)
        usage = self._extract_usage(response)
        return ClientRunResult(exit_code=0, stdout=text, token_usage=usage)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_key_value(self) -> str:
        key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it or pass api_key= to OpenAIDirectAdapter."
            )
        return key

    def _build_body(self, request: MlRequest) -> Dict[str, Any]:
        system_parts = []
        if request.context:
            system_parts.append(request.context)
        if request.user_system_prompt:
            system_parts.append(request.user_system_prompt)
        body: Dict[str, Any] = {
            "model": request.model,
            "input": [{"role": "user", "content": request.prompt}],
        }
        if system_parts:
            body["instructions"] = "\n\n".join(system_parts)
        return body

    def list_models(self) -> List[ModelInfo]:
        """Return OpenAI language models owned by openai."""
        data = self._get("/models")
        return [
            ModelInfo(id=m["id"], name=m["id"])
            for m in data.get("data", [])
            if m.get("owned_by") == "openai"
        ]

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key_value()}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            _BASE_URL + path,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {error_body}") from exc

    def _get(self, path: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            _BASE_URL + path,
            headers=self._headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {error_body}") from exc

    def _extract_text(self, response: Dict[str, Any]) -> str:
        # Traverse output[*].content[*] and collect parts with type "output_text".
        texts = []
        for item in response.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        texts.append(part.get("text", ""))
        text = "".join(texts)
        if not text:
            return "\n"
        return text if text.endswith("\n") else text + "\n"

    def _extract_usage(self, response: Dict[str, Any]) -> TokenUsage:
        u = response.get("usage", {})
        details_in = u.get("input_tokens_details") or {}
        details_out = u.get("output_tokens_details") or {}
        return TokenUsage(
            input_tokens=int_or_none(u.get("input_tokens")),
            output_tokens=int_or_none(u.get("output_tokens")),
            cache_read_tokens=int_or_none(details_in.get("cached_tokens")),
            cache_write_tokens=None,  # OpenAI's cache is automatic read-only
            reasoning_tokens=int_or_none(details_out.get("reasoning_tokens")),
            cost_usd=None,
            raw=dict(u),
        )
