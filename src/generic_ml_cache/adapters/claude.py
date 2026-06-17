# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

from typing import List, Optional

from .base import ClientAdapter
from .registry import register


class ClaudeAdapter(ClientAdapter):
    name = "claude"
    default_executable = "claude"

    def build_argv(
        self, executable, run_dir, model, effort, context, prompt, system_prompt
    ) -> List[str]:
        # The prompt and context are delivered on stdin (see stdin_payload), never
        # as an argv argument, so an arbitrarily large prompt cannot hit the OS
        # single-argument size limit. With -p/--print and no prompt argument,
        # Claude reads the prompt from stdin.
        argv = [executable, "-p", "--model", model]
        # Effort is optional: when omitted, let Claude apply its own per-model
        # default rather than passing an empty (and invalid) --effort value.
        if effort:
            argv += ["--effort", effort]
        argv += self.write_access_argv(run_dir)
        argv += ["--append-system-prompt", system_prompt, "--output-format", "text"]
        return argv

    def stdin_payload(self, context, prompt, system_prompt) -> Optional[str]:
        # Prompt + context go to the client on stdin. The system prompt is a
        # separate, small argv flag (--append-system-prompt), so it stays in argv.
        return f"{context}\n\n{prompt}" if context else prompt

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
