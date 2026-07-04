# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedLocalRequest — what core passes to a LocalClientPort for managed execution."""

from __future__ import annotations

from dataclasses import dataclass


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
    allowed_read_paths: tuple[str, ...] = ()
    add_dir_paths: tuple[str, ...] = ()
    client_args: tuple[str, ...] = ()
    grants: frozenset[str] = frozenset()
    timeout: float | None = None
    stream_path: str | None = None

    def __post_init__(self) -> None:
        for name in ("allowed_read_paths", "add_dir_paths", "client_args"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "grants", frozenset(self.grants))
