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
        # The prompt is delivered on stdin (see stdin_payload), not as an argv
        # argument, so a large prompt cannot hit the OS argument-size limit. With
        # --print and piped stdin, cursor-agent reads the prompt from stdin.
        # Cursor encodes effort in the model id. Pass a full id from --list-models
        # with no effort (preferred), or a base id plus an effort to append. Do not
        # pass both, or the effort is duplicated.
        model_id = f"{model}-{effort}" if effort else model
        return [
            executable,
            *self.write_access_argv(run_dir),
            "--model",
            model_id,
            "--print",
        ]

    def stdin_payload(self, context, prompt, system_prompt) -> Optional[str]:
        # Current cursor-agent has NO system-prompt flag (it was removed), and
        # headless --print ignores workspace rule files (.cursor/rules,
        # .cursorrules, AGENTS.md) -- both verified against the live CLI. The only
        # reliable channel is the prompt itself, so the prime directive (system
        # prompt) and the context are folded into the stdin payload here. None of
        # this enters the Request, so input_data and the cache key are unchanged --
        # cursor keys identically to claude/codex; the directive is delivered
        # out-of-key exactly as the others' system-prompt flags are.
        segments = [system_prompt] if system_prompt else []
        if context:
            segments.append(context)
        segments.append(prompt)
        return "\n\n".join(segments)

    def write_access_argv(self, run_dir):
        # cursor-agent refuses an untrusted workspace ("Workspace Trust Required")
        # in the isolated run folder. --trust accepts it; in --print mode the agent
        # already has its write tool, so trust alone is sufficient to write (the
        # separate --force is not needed). Reads outside the folder are unaffected.
        # Verified against cursor-agent --print on the live CLI.
        return ["--trust"]

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
