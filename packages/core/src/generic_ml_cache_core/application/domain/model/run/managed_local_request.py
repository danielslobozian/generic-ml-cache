# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedLocalRequest — what core passes to a LocalClientPort for managed execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


@dataclass(frozen=True)
class ManagedLocalRequest:
    """Application-level description of a managed local execution.

    Carries the user's intent in user terms. The local client adapter translates
    this into client-specific subprocess flags, config files, and environment.

    The core owns the *policy* (run this prompt in an isolated workspace, capture
    artifacts, honour these grants). The adapter owns the *translation* (how
    Claude/Codex/Cursor actually express that policy via their own CLI).
    """

    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: Optional[str] = None
    allowed_read_paths: List[str] = field(default_factory=list)
    add_dir_paths: List[str] = field(default_factory=list)
    client_args: List[str] = field(default_factory=list)
    grants: FrozenSet[str] = field(default_factory=frozenset)
    timeout: Optional[float] = None
    stream_path: Optional[str] = None
