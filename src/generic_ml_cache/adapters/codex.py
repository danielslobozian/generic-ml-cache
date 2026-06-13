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
        argv = [executable, "exec", *self.write_access_argv(run_dir), "--model", model]
        # Effort is optional: when omitted, leave model_reasoning_effort unset so
        # Codex uses the model's own default instead of an empty override.
        if effort:
            argv += ["-c", f"model_reasoning_effort={effort}"]
        argv += ["-c", f"experimental_instructions={system_prompt}", full_prompt]
        return argv

    def write_access_argv(self, run_dir):
        # The isolated run folder is not a git repo, so codex refuses to run
        # ("Not inside a trusted directory") without --skip-git-repo-check; and
        # the default read-only sandbox lets it run but never write. workspace-write
        # makes the run folder writable (its writable set already includes the cwd
        # and /tmp); -C pins that folder as the explicit write fence. Reads outside
        # are unaffected. Verified against codex exec on the live CLI.
        return ["--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(run_dir)]
