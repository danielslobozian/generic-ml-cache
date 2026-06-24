# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.common.checksum import checksum_input_data


@dataclass(frozen=True)
class ApiCallIdentity(CallIdentity):
    """The identity of a direct API call.

    Addressed by provider, model, and fingerprints of context, prompt, and
    optional system prompt. The kind is folded into the key so an API call
    can never collide with a local managed or passthrough call. Raw text is
    never stored — only checksums enter the key.
    """

    provider: str
    model: str
    context_fingerprint: str
    prompt_fingerprint: str
    system_fingerprint: Optional[str] = None
    effort: str = ""

    def generate_key(self) -> str:
        data = {
            "kind": ExecutionKind.API.value,
            "provider": self.provider,
            "model": self.model,
            "context": self.context_fingerprint,
            "prompt": self.prompt_fingerprint,
            "effort": self.effort,
        }
        if self.system_fingerprint:
            data["system"] = self.system_fingerprint
        return checksum_input_data(data)
