# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GatewayRequest - immutable value object for an incoming Anthropic-compatible API call."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.model.usage.usage import int_or_none
from generic_ml_cache_core.common.immutable import deep_freeze, thaw

_ANTHROPIC_CLIENT = "anthropic"


@dataclass(frozen=True)
class GatewayRequest:
    """The incoming request to the caching gateway proxy.

    Holds the *entire* request body as received from the API client. A transparent
    proxy must neither drop nor reorder fields: every field the caller sent is
    forwarded upstream verbatim, and every field is part of the cache identity — so
    two requests that differ in any way (``temperature``, ``tools``, ``stop_sequences``,
    ``max_tokens`` …) never collide on one cached response.

    The body is **deep-frozen** at construction (``MappingProxyType`` + tuples, all
    the way down). The gateway both *keys on* and *forwards* the body, so a mutable
    body would open a TOCTOU gap between what was keyed/recorded and what is actually
    forwarded; one frozen snapshot guarantees keyed ≡ forwarded ≡ recorded.
    """

    body: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", deep_freeze(self.body))

    @property
    def model(self) -> str:
        value = self.body.get("model")
        return value if isinstance(value, str) else ""

    @property
    def messages(self) -> Any:
        return self.body.get("messages")

    @property
    def system(self) -> Any:
        return self.body.get("system")

    @property
    def max_tokens(self) -> Any:
        return self.body.get("max_tokens")

    def generate_cache_key(self) -> str:
        """Return a deterministic SHA-256 hex key over the *whole* request body.

        Every field the caller sent can change the response (or is part of wire
        fidelity), so none is silently dropped from the key — soundness over
        hit-rate. ``max_tokens`` is included: a smaller cap can truncate the output.
        """
        payload = json.dumps(thaw(self.body), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def serialize_request(self) -> bytes:
        """Return the upstream JSON request body — the caller's body, verbatim."""
        return json.dumps(thaw(self.body), sort_keys=True).encode("utf-8")

    def request_model(self) -> str:
        """Return the model identifier used for metrics."""
        return self.model

    def client_name(self) -> str:
        """Return the gateway client name used for metrics."""
        return _ANTHROPIC_CLIENT

    def is_cacheable(self) -> bool:
        """Return whether this request may be cached."""
        return True

    def parse_token_usage(self, response_body_bytes: bytes) -> TokenUsage | None:
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
