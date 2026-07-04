# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ProbeCommand."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.service.cacheability import is_call_uncacheable


@dataclass(frozen=True)
class ProbeCommand:
    """The input to the probe use case: the key-determining inputs only.

    A probe is a read-only forecast, so it carries no run *policy* (no cache mode,
    no persist/record flags). It does carry every *keyed* input — including the
    system prompt — so a probe and a run derive the same key from the shared builder.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: str | None = None
    input_file_paths: tuple[str, ...] = ()
    allow_paths: tuple[str, ...] = ()
    scan_trust: bool = False
    client_args: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("input_file_paths", "allow_paths", "client_args", "grants"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    @property
    def is_uncacheable(self) -> bool:
        return is_call_uncacheable(self.allow_paths, self.scan_trust)
