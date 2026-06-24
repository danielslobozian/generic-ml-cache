# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""API adapter package — direct REST adapters for ML providers.

Importing this package registers the built-in API adapters so callers can
resolve a provider name (e.g. ``"gemini"``) via :func:`get_api_adapter` without
knowing the concrete class.
"""

from __future__ import annotations

from generic_ml_cache_core.adapter.out.api.api_registry import (
    get_api_adapter,
    register_api_adapter,
    registered_api_names,
)
from generic_ml_cache_core.adapter.out.api.anthropic_direct_adapter import AnthropicDirectAdapter
from generic_ml_cache_core.adapter.out.api.gemini_direct_adapter import GeminiDirectAdapter
from generic_ml_cache_core.adapter.out.api.openai_direct_adapter import OpenAIDirectAdapter

register_api_adapter("anthropic", lambda api_key: AnthropicDirectAdapter(api_key=api_key))
register_api_adapter("gemini", lambda api_key: GeminiDirectAdapter(api_key=api_key))
register_api_adapter("openai", lambda api_key: OpenAIDirectAdapter(api_key=api_key))

__all__ = ["get_api_adapter", "register_api_adapter", "registered_api_names"]
