# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for OpenAI's Codex CLI (non-interactive).

Effort maps to ``model_reasoning_effort``. Flags
are best-effort for v0.0.1 and are easy to correct here; the executable seam
lets you point at any binary.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
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
        # Capability doors (sandbox write, network, web-search) now live in
        # $CODEX_HOME/config.toml written by grant_setup -- not in argv. build_argv
        # carries only transport: the exec subcommand, JSON events, the no-git-repo
        # escape and the cwd fence, model + effort, the system prompt, passthrough,
        # and the trailing stdin marker.
        argv = [
            executable,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(run_dir),
            "--model",
            model,
        ]
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

    def grant_setup(self, run_dir, config_home, grants):
        # Uniform door: write $CODEX_HOME/config.toml so the FILE enables
        # capabilities. The run folder is untrusted (a fresh temp dir), so a
        # folder-local .codex/config.toml would be skipped -- we redirect the home
        # instead and seed auth.json into it. workspace-write is always on (the
        # record-path guarantee); it already permits read + shell, so granting
        # those needs nothing extra (Codex exposes no file-level read/shell *deny*
        # -- a documented limit, not a door we close). net flips network_access on;
        # web-search sets web_search=live. The cache enables (docs/grants.md).
        lines = ['approval_policy = "never"', 'sandbox_mode = "workspace-write"']
        if "web-search" in grants:
            lines.append('web_search = "live"')
        if "net" in grants:
            lines += ["[sandbox_workspace_write]", "network_access = true"]
        config_home.mkdir(parents=True, exist_ok=True)
        (config_home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        auth = Path.home() / ".codex" / "auth.json"
        if auth.is_file():
            try:
                shutil.copy2(auth, config_home / "auth.json")
            except OSError:
                pass  # best-effort; an env API key still authenticates the run
        return {"CODEX_HOME": str(config_home)}
