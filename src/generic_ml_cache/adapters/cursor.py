# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for the Cursor agent CLI.

Cursor bakes reasoning effort into the model id, so ``effort`` is appended to
the model string. Best-effort for v0.0.1; correct here as needed.
"""

from __future__ import annotations

from typing import List

from .base import ClientAdapter


class CursorAdapter(ClientAdapter):
    name = "cursor"
    default_executable = "cursor-agent"

    def build_argv(
        self, executable, run_dir, model, effort, context, prompt, system_prompt
    ) -> List[str]:
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        model_id = f"{model}-{effort}" if effort else model
        return [
            executable,
            "--model",
            model_id,
            "--system-prompt",
            system_prompt,
            "--print",
            full_prompt,
        ]
