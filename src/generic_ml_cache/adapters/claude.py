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
        return [
            executable,
            "-p",
            full_prompt,
            "--model",
            model,
            "--effort",
            effort,
            "--append-system-prompt",
            system_prompt,
            "--output-format",
            "text",
        ]


register(ClaudeAdapter())
