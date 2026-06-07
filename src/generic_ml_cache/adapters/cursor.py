# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for the Cursor agent CLI.

Cursor bakes reasoning effort into the model id, so ``effort`` is appended to
the model string. Best-effort for v0.0.1; correct here as needed.
"""

from __future__ import annotations

from typing import List, Optional

from .base import ClientAdapter, ModelInfo


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

    def models_argv(self, executable: str) -> Optional[List[str]]:
        return [executable, "--list-models"]

    def parse_model_list(self, stdout: str) -> List[ModelInfo]:
        """Parse ``cursor-agent --list-models`` output.

        Each model is one ``<id> - <Label>`` line. A header line and a trailing
        ``Tip:`` line are ignored; a ``(default)``/``(current)`` marker on the
        label is lifted into a flag. The id is taken verbatim -- it is exactly
        what a caller passes to ``--model``.
        """
        models: List[ModelInfo] = []
        for raw in stdout.splitlines():
            line = raw.strip()
            if not line or " - " not in line:
                continue
            if line.lower().startswith("available models") or line.startswith("Tip:"):
                continue
            ident, _, label = line.partition(" - ")
            ident, label = ident.strip(), label.strip()
            if not ident:
                continue
            default = current = False
            if label.endswith("(default)"):
                default, label = True, label[: -len("(default)")].strip()
            elif label.endswith("(current)"):
                current, label = True, label[: -len("(current)")].strip()
            models.append(ModelInfo(id=ident, name=label, default=default, current=current))
        return models
