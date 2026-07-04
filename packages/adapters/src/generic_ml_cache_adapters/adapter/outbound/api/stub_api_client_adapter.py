# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StubApiClientAdapter: a deterministic, offline stand-in for a provider API."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.outbound.api_client_port import ApiClientPort


class StubApiClientAdapter(ApiClientPort):
    """A deterministic stand-in for a real provider API.

    It runs everywhere — including CI, where no provider is reachable — by
    synthesising a reply from the inputs: stdout echoes the prompt, and the
    token usage is a deterministic function of the input sizes. Same inputs ->
    same result, so it behaves correctly under caching. Swap in a real adapter
    when one exists; the port contract is identical.
    """

    name = "stub-api"

    def run(self, request: MlRequest) -> ClientRunResult:
        reply = f"[stub:{request.model}] {request.prompt}"
        input_tokens = len(request.context) + len(request.prompt)
        token_usage = TokenUsage(input_tokens=input_tokens, output_tokens=len(reply))
        return ClientRunResult(exit_code=0, stdout=reply, token_usage=token_usage)
