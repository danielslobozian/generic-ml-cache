# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientAnswer — what a local client adapter returns from making its call.

The adapter's job is to translate a request into an answer: run the client and
map its output to this. It is deliberately *files-free* — capturing generated
artifacts is the managed-execution use case's job (it owns the workspace), not
the adapter's. Core combines this answer with the captured files into the full
ClientRunResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage


@dataclass(frozen=True)
class ClientAnswer:
    """The exit code, streams, and usage the client reported — no artifacts."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    token_usage: Optional[TokenUsage] = None
