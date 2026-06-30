# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedLocalRequest — what core passes to a LocalClientPort for managed execution."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    user_system_prompt: str | None = None
    allowed_read_paths: list[str] = field(default_factory=list)
    add_dir_paths: list[str] = field(default_factory=list)
    client_args: list[str] = field(default_factory=list)
    grants: frozenset[str] = field(default_factory=frozenset)
    timeout: float | None = None
    stream_path: str | None = None
