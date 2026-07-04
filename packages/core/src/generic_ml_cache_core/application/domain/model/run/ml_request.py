# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlRequest — the unified runner port DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MlRequest:
    """What the use case passes to any MlRunnerPort implementation.

    Carries the user's intent in user terms — model, effort, context, prompt,
    file paths, folder grants. The adapter translates this into whatever wire
    format or subprocess flags its client expects. No client name: by the time
    run() is called, the correct adapter is already selected.

    Cache-policy fields (cache_mode, persistence_depth, scan_trust) are absent
    — they are the use case's concern, not the runner's.
    """

    model: str
    effort: str
    context: str
    prompt: str
    input_file_paths: tuple[str, ...] = ()
    allow_paths: tuple[str, ...] = ()
    client_args: tuple[str, ...] = ()
    grants: frozenset[str] = frozenset()
    user_system_prompt: str | None = None

    def __post_init__(self) -> None:
        for name in ("input_file_paths", "allow_paths", "client_args"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "grants", frozenset(self.grants))
