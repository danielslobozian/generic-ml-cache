# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

from typing import List

from .base import ClientAdapter
from .registry import register


class ClaudeAdapter(ClientAdapter):
    name = "claude"
    default_executable = "claude"

    def build_argv(
        self, executable, run_dir, model, effort, context, prompt, system_prompt
    ) -> List[str]:
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        argv = [executable, "-p", full_prompt, "--model", model]
        # Effort is optional: when omitted, let Claude apply its own per-model
        # default rather than passing an empty (and invalid) --effort value.
        if effort:
            argv += ["--effort", effort]
        argv += self.write_access_argv(run_dir)
        argv += ["--append-system-prompt", system_prompt, "--output-format", "text"]
        return argv

    def read_access_argv(self, paths):
        # Claude Code grants read access to extra directories via --add-dir.
        argv = []
        for p in paths:
            argv += ["--add-dir", p]
        return argv

    def write_access_argv(self, run_dir):
        # Headless Claude pauses on a write-permission prompt and only narrates
        # the file. acceptEdits auto-approves edits/writes (the run folder is the
        # cwd); it does NOT grant reads outside the folder. Verified to flip a
        # file-producing call from narrate-only to a real write; the broader
        # --dangerously-skip-permissions is unnecessary here.
        return ["--permission-mode", "acceptEdits"]


register(ClaudeAdapter())
