# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GatewayRequest - immutable value object for an incoming Anthropic-compatible API call."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none

_ANTHROPIC_CLIENT = "anthropic"


@dataclass(frozen=True)
class GatewayRequest:
    """The incoming request to the caching gateway proxy.

    Holds the raw wire-level fields as received from the API client.
    ``generate_cache_key`` is the single source of truth for the cache key
    produced from this request.
    """

    model: str
    messages: list
    system: Optional[object]
    max_tokens: int

    def generate_cache_key(self) -> str:
        """Return a deterministic SHA-256 hex key for this request.

        Only the semantic fields that determine the response are hashed:
        ``model``, ``messages``, and ``system``. ``max_tokens`` is excluded
        because a different token cap does not produce a semantically different
        cached response.
        """
        payload = json.dumps(
            {"model": self.model, "messages": self.messages, "system": self.system},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def serialize_request(self) -> bytes:
        """Return the upstream JSON request body."""
        request_body: dict = {
            "model": self.model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
        }
        if self.system is not None:
            request_body["system"] = self.system
        return json.dumps(request_body, sort_keys=True).encode("utf-8")

    def request_model(self) -> str:
        """Return the model identifier used for metrics."""
        return self.model

    def client_name(self) -> str:
        """Return the gateway client name used for metrics."""
        return _ANTHROPIC_CLIENT

    def is_cacheable(self) -> bool:
        """Return whether this request may be cached."""
        return True

    def parse_token_usage(self, response_body_bytes: bytes) -> Optional[TokenUsage]:
        """Parse Anthropic token usage from the upstream response body."""
        try:
            usage = json.loads(response_body_bytes).get("usage", {})
            return TokenUsage(
                input_tokens=int_or_none(usage.get("input_tokens")),
                output_tokens=int_or_none(usage.get("output_tokens")),
                cache_read_tokens=int_or_none(usage.get("cache_read_input_tokens")),
                cache_write_tokens=int_or_none(usage.get("cache_creation_input_tokens")),
                raw=dict(usage),
            )
        except (json.JSONDecodeError, AttributeError, TypeError, UnicodeDecodeError):
            return None
