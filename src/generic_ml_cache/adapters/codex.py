# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for OpenAI's Codex CLI (non-interactive).

Effort maps to ``model_reasoning_effort``. Flags
are best-effort for v0.0.1 and are easy to correct here; the executable seam
lets you point at any binary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..usage import ParsedOutput, Usage, int_or_none
from .base import ClientAdapter


class CodexAdapter(ClientAdapter):
    name = "codex"
    default_executable = "codex"

    def build_argv(
        self,
        executable,
        run_dir,
        model,
        effort,
        context,
        prompt,
        system_prompt,
        client_args=(),
        grants=(),
    ) -> List[str]:
        argv = [executable, "exec", "--json", *self.write_access_argv(run_dir)]
        if "net" in grants:
            argv += self.network_access_argv()
        argv += ["--model", model]
        # Effort is optional: when omitted, leave model_reasoning_effort unset so
        # Codex uses the model's own default instead of an empty override.
        if effort:
            argv += ["-c", f"model_reasoning_effort={effort}"]
        # The prompt + context are delivered on stdin (see stdin_payload), so a
        # large prompt cannot exceed the OS argument-size limit. The trailing "-"
        # tells `codex exec` to read the prompt from stdin instead of an argv
        # argument; communicate() then closes stdin on EOF, which also avoids the
        # "reading additional input from stdin" hang codex shows in a non-TTY child
        # when a prompt argument is given but stdin is left open. The system prompt
        # is a small config value and stays in argv.
        argv += ["-c", f"experimental_instructions={system_prompt}"]
        # Passthrough args before the trailing "-" (the stdin marker, codex's last
        # positional), so they are still parsed as flags. Appended verbatim.
        argv += client_args
        argv.append("-")
        return argv

    def stdin_payload(self, context, prompt, system_prompt) -> Optional[str]:
        return f"{context}\n\n{prompt}" if context else prompt

    def parse_output(self, stdout: str) -> ParsedOutput:
        """Codex's ``--json`` output is a JSON-lines *stream* of events, one per
        line. The answer text is the ``text`` of the final ``agent_message`` item;
        the usage is the ``usage`` block on the final ``turn.completed`` event.
        Codex reports reasoning tokens *separately* from output, reports no
        cache-write count (so that stays unknown), and reports no cost.
        """
        answer: Optional[str] = None
        usage_block: Optional[Dict[str, Any]] = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a stray non-JSON line in the stream
            if not isinstance(event, dict):
                continue
            if event.get("type") == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str):
                        answer = text  # keep the latest; the final one is the answer
            elif event.get("type") == "turn.completed":
                block = event.get("usage")
                if isinstance(block, dict):
                    usage_block = block

        if answer is None:
            # Never found the answer event -- hand back the raw stream, no usage.
            return ParsedOutput(text=stdout, usage=None)

        usage = None
        if usage_block is not None:
            usage = Usage(
                input_tokens=int_or_none(usage_block.get("input_tokens")),
                output_tokens=int_or_none(usage_block.get("output_tokens")),
                cache_read_tokens=int_or_none(usage_block.get("cached_input_tokens")),
                # Codex reports no cache-write count: unknown, not zero.
                cache_write_tokens=None,
                reasoning_tokens=int_or_none(usage_block.get("reasoning_output_tokens")),
                cost_usd=None,
                raw=dict(usage_block),
            )
        return ParsedOutput(text=answer, usage=usage)

    def write_access_argv(self, run_dir):
        # The isolated run folder is not a git repo, so codex refuses to run
        # ("Not inside a trusted directory") without --skip-git-repo-check; and
        # the default read-only sandbox lets it run but never write. workspace-write
        # makes the run folder writable (its writable set already includes the cwd
        # and /tmp); -C pins that folder as the explicit write fence. Reads outside
        # are unaffected. Verified against codex exec on the live CLI.
        return ["--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(run_dir)]

    def network_access_argv(self):
        # Open the network inside the workspace-write sandbox the run already uses.
        # Codex leaves it off by default; this flips network_access on for this run
        # only. The probes confirmed the toggle gates the network at the process
        # level (off = an outbound fetch is blocked, on = it reaches) -- the one
        # leak-proof network door of the three clients. The -c override mirrors how
        # this adapter already sets model_reasoning_effort, and is verified against
        # the live CLI through the cache (grant on -> an external fetch reaches;
        # off -> blocked at the sandbox).
        return ["-c", "sandbox_workspace_write.network_access=true"]
