# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiClientPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.message import Message


class ApiClientPort(ABC):
    """Outbound port for calling an ML provider API directly.

    Distinct from the local runner ports: there is no subprocess, no filesystem,
    and no grants — the caller has already built the full message list. The
    adapter returns a raw ClientRunResult with the response text as stdout, an
    empty file list, and the provider-reported token usage when available.
    """

    @abstractmethod
    def run(
        self, provider: str, model: str, messages: List[Message], effort: str = ""
    ) -> ClientRunResult:
        """Call ``provider``'s ``model`` with ``messages`` and return the raw
        result. ``effort`` maps to the provider's reasoning-depth control when
        non-empty (e.g. Gemini thinkingLevel, Anthropic thinking budget).
        Raises on an unrecoverable transport failure."""
