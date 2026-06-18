# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..usage import ParsedOutput, Usage, float_or_none, int_or_none
from .base import ClientAdapter
from .registry import register


class ClaudeAdapter(ClientAdapter):
    name = "claude"
    default_executable = "claude"

    def build_argv(
        self, executable, run_dir, model, effort, context, prompt, system_prompt, client_args=()
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
        # JSON output so the call also returns its usage (tokens + Claude's own
        # cost estimate). parse_output lifts the answer text back out of the JSON.
        argv += ["--append-system-prompt", system_prompt, "--output-format", "json"]
        # Passthrough args go last: Claude takes the prompt on stdin, so there is no
        # trailing positional to sit in front of. Appended verbatim, uninterpreted.
        argv += client_args
        return argv

    def parse_output(self, stdout: str) -> ParsedOutput:
        """Claude's headless JSON is a single object: ``result`` is the answer
        text, ``usage`` holds the (primary-model) token counts, ``total_cost_usd``
        is the cumulative cost estimate across every model the run used, and
        ``modelUsage`` breaks it down per model (the main model plus any subagent
        models). The per-model breakdown is kept verbatim in ``raw``; the
        normalized counts come from the headline ``usage`` block, the cost from the
        cumulative ``total_cost_usd``.
        """
        try:
            doc = json.loads(stdout)
            if not isinstance(doc, dict):
                raise ValueError("expected a JSON object")
        except (json.JSONDecodeError, ValueError):
            return ParsedOutput(text=stdout, usage=None)

        text = doc.get("result")
        if not isinstance(text, str):
            # Not the shape we expected -- keep the raw output, skip usage.
            return ParsedOutput(text=stdout, usage=None)

        block = doc.get("usage") if isinstance(doc.get("usage"), dict) else {}
        raw: Dict[str, Any] = {}
        for key in ("usage", "modelUsage", "total_cost_usd"):
            if key in doc:
                raw[key] = doc[key]

        usage = Usage(
            input_tokens=int_or_none(block.get("input_tokens")),
            output_tokens=int_or_none(block.get("output_tokens")),
            cache_read_tokens=int_or_none(block.get("cache_read_input_tokens")),
            cache_write_tokens=int_or_none(block.get("cache_creation_input_tokens")),
            # Claude folds reasoning into output_tokens; it is not separable here.
            reasoning_tokens=None,
            cost_usd=float_or_none(doc.get("total_cost_usd")),
            raw=raw,
        )
        return ParsedOutput(text=text, usage=usage)

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
