# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ProbeCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from generic_ml_cache.application.domain.service.cacheability import is_call_uncacheable


@dataclass(frozen=True)
class ProbeCommand:
    """The input to the probe use case: the key-determining inputs only.

    A probe is a read-only forecast, so it carries no run policy (no cache mode,
    no persist/record flags, no system prompt). It exposes the same keyed fields a
    run does, so both derive the same key from the shared builder.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    input_file_paths: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    scan_trust: bool = False
    client_args: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)

    @property
    def is_uncacheable(self) -> bool:
        return is_call_uncacheable(self.allow_paths, self.scan_trust)
