# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StubApiClientAdapter: a deterministic, offline stand-in for a provider API."""

from __future__ import annotations

from typing import List

from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.message import Message
from generic_ml_cache.application.domain.model.token_usage import TokenUsage
from generic_ml_cache.application.port.out.api_client_port import ApiClientPort


class StubApiClientAdapter(ApiClientPort):
    """A deterministic stand-in for a real provider API.

    It runs everywhere — including CI, where no provider is reachable — by
    synthesising a reply from the inputs: stdout echoes the last message, and the
    token usage is a deterministic function of the message sizes. Same inputs ->
    same result, so it behaves correctly under caching. Swap in a real adapter
    when one exists; the port contract is identical.
    """

    def run(self, provider: str, model: str, messages: List[Message]) -> ClientRunResult:
        last_content = messages[-1].content if messages else ""
        reply = f"[stub:{provider}:{model}] {last_content}"
        input_tokens = sum(len(message.content) for message in messages)
        token_usage = TokenUsage(input_tokens=input_tokens, output_tokens=len(reply))
        return ClientRunResult(exit_code=0, stdout=reply, token_usage=token_usage)
