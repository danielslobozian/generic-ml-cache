# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for OpenAI's Codex CLI (non-interactive).

Effort maps to ``model_reasoning_effort``. Flags
are best-effort for v0.0.1 and are easy to correct here; the executable seam
lets you point at any binary.
"""

from __future__ import annotations

from typing import List

from .base import ClientAdapter


class CodexAdapter(ClientAdapter):
    name = "codex"
    default_executable = "codex"

    def build_argv(
        self, executable, run_dir, model, effort, context, prompt, system_prompt
    ) -> List[str]:
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        return [
            executable,
            "exec",
            "--model",
            model,
            "-c",
            f"model_reasoning_effort={effort}",
            "-c",
            f"experimental_instructions={system_prompt}",
            full_prompt,
        ]
