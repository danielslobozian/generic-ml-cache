# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlRequest — the unified runner port DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


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
    input_file_paths: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    client_args: List[str] = field(default_factory=list)
    native_args: List[str] = field(default_factory=list)
    grants: FrozenSet[str] = field(default_factory=frozenset)
    user_system_prompt: Optional[str] = None
