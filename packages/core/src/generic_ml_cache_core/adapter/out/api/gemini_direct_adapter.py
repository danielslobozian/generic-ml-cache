# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GeminiDirectAdapter: calls Google's Gemini generateContent REST endpoint."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.message import Message
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiDirectAdapter(ApiClientPort):
    """Calls Google's Gemini generateContent REST API using stdlib urllib.

    Auth: reads GEMINI_API_KEY from the environment, or accepts api_key= at
    construction time. System-role messages map to systemInstruction; user and
    assistant messages map to contents entries with roles "user" and "model".
    ThoughtsTokenCount is captured as reasoning_tokens; cache_write_tokens and
    cost_usd are always None (Gemini does not report them per call).
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def run(
        self, provider: str, model: str, messages: List[Message], effort: str = ""
    ) -> ClientRunResult:
        body = self._build_body(messages, effort)
        url = f"{_BASE_URL}/{model}:generateContent"
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
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Export it or pass api_key= to GeminiDirectAdapter."
            )
        return key

    def _build_body(self, messages: List[Message], effort: str = "") -> Dict[str, Any]:
        system_parts = [{"text": m.content} for m in messages if m.role == "system"]
        contents = [
            {
                "role": "model" if m.role in ("assistant", "model") else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role != "system"
        ]
        body: Dict[str, Any] = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        if effort:
            body["generationConfig"] = {"thinkingConfig": {"thinkingLevel": effort}}
        return body

    def _post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": self._api_key_value(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API error {exc.code}: {error_body}") from exc

    def _extract_text(self, response: Dict[str, Any]) -> str:
        candidates = response.get("candidates", [])
        if not candidates:
            return "\n"
        parts = candidates[0].get("content", {}).get("parts", [])
        # Collect only parts that carry text; thoughtSignature and other
        # non-text fields may appear alongside text in thinking-enabled models.
        text = "".join(p["text"] for p in parts if "text" in p)
        return text if text.endswith("\n") else text + "\n"

    def _extract_usage(self, response: Dict[str, Any]) -> TokenUsage:
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
