# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AnthropicDirectAdapter: calls Anthropic's Messages REST endpoint."""

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

_BASE_URL = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"


@adapter
class AnthropicDirectAdapter(ApiClientPort, ModelListingPort):
    """Calls Anthropic's Messages API using stdlib urllib.

    Auth: reads ANTHROPIC_API_KEY from the environment, or accepts api_key= at
    construction time. context and user_system_prompt map to the 'system' field;
    prompt maps to a user message. Anthropic is the only provider that fills
    cache_write_tokens. reasoning_tokens is None (thinking folds into
    output_tokens). cost_usd is always None (Anthropic does not return it).
    """

    name = "anthropic"
    _DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._max_tokens = max_tokens

    def run(self, request: MlRequest) -> ClientRunResult:
        body = self._build_body(request)
        response = self._post("/messages", body)
        text = self._extract_text(response)
        usage = self._extract_usage(response)
        return ClientRunResult(exit_code=0, stdout=text, token_usage=usage)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_key_value(self) -> str:
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it or pass api_key= to AnthropicDirectAdapter."
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
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        return body

    def list_models(self) -> List[ModelInfo]:
        """Return available Anthropic language models."""
        data = self._get("/models")
        return [
            ModelInfo(id=m["id"], name=m.get("display_name", m["id"]))
            for m in data.get("data", [])
            if m.get("type") == "model"
        ]

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self._api_key_value(),
            "anthropic-version": _API_VERSION,
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
            raise RuntimeError(f"Anthropic API error {exc.code}: {error_body}") from exc

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
            raise RuntimeError(f"Anthropic API error {exc.code}: {error_body}") from exc

    def _extract_text(self, response: Dict[str, Any]) -> str:
        content = response.get("content", [])
        # Collect only text blocks; thinking blocks (type="thinking") are ignored.
        text = "".join(block["text"] for block in content if block.get("type") == "text")
        if not text:
            return "\n"
        return text if text.endswith("\n") else text + "\n"

    def _extract_usage(self, response: Dict[str, Any]) -> TokenUsage:
        u = response.get("usage", {})
        return TokenUsage(
            input_tokens=int_or_none(u.get("input_tokens")),
            output_tokens=int_or_none(u.get("output_tokens")),
            cache_read_tokens=int_or_none(u.get("cache_read_input_tokens")),
            cache_write_tokens=int_or_none(u.get("cache_creation_input_tokens")),
            reasoning_tokens=None,  # Anthropic folds thinking into output_tokens
            cost_usd=None,  # Anthropic API does not report cost per call
            raw=dict(u),
        )
