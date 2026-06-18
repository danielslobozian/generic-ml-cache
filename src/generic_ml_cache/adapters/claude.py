# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..usage import ParsedOutput, Usage, float_or_none, int_or_none
from .base import ClientAdapter
from .registry import register


class ClaudeAdapter(ClientAdapter):
    name = "claude"
    default_executable = "claude"

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
        # The prompt and context are delivered on stdin (see stdin_payload), never
        # as an argv argument, so an arbitrarily large prompt cannot hit the OS
        # single-argument size limit. With -p/--print and no prompt argument,
        # Claude reads the prompt from stdin.
        # Capability doors (write/read/shell/net/web-search) now live in a config
        # FILE written by grant_setup into CLAUDE_CONFIG_DIR -- not in argv.
        # build_argv carries only transport: print mode, model, effort, the system
        # prompt, JSON output (so usage comes back), and the verbatim passthrough.
        argv = [executable, "-p", "--model", model]
        # Effort is optional: when omitted, let Claude apply its own per-model
        # default rather than passing an empty (and invalid) --effort value.
        if effort:
            argv += ["--effort", effort]
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

    def grant_setup(self, run_dir, config_home, grants):
        # Uniform door: write settings.json into a redirected CLAUDE_CONFIG_DIR so
        # the FILE (not a flag) enables capabilities. Verified against the live CLI:
        # the redirected home governs because the run folder is clean of a project
        # .claude/ that would outrank it. acceptEdits + Write/Edit are always on so
        # a file-producing call actually writes (the record-path guarantee); each
        # named grant ADDS its allow-token. The cache enables; it never closes
        # (docs/grants.md).
        allow = ["Write(**)", "Edit(**)"]
        if "read" in grants:
            allow.append("Read(**)")
        if "shell" in grants:
            allow.append("Bash(**)")
        if "net" in grants:
            allow.append("WebFetch")
        if "web-search" in grants:
            allow.append("WebSearch")
        settings = {"permissions": {"allow": allow}, "defaultMode": "acceptEdits"}
        config_home.mkdir(parents=True, exist_ok=True)
        (config_home / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        # Seed credentials so the relocated home is authenticated. Subscription
        # login lives in ~/.claude; an API key in the env carries over on its own.
        # Bulk caches (projects/history/todos/shell-snapshots) are skipped; a stray
        # settings.local.json would outrank ours, so it is dropped.
        src = Path.home() / ".claude"
        if src.is_dir():
            skip = {
                "projects",
                "history",
                "todos",
                "shell-snapshots",
                "settings.json",
                "settings.local.json",
            }
            for child in src.iterdir():
                if child.name in skip:
                    continue
                dest = config_home / child.name
                try:
                    if child.is_dir():
                        shutil.copytree(child, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(child, dest)
                except OSError:
                    pass  # best-effort seeding; an env API key still authenticates
        # Claude Code also keeps a top-level ~/.claude.json (account, onboarding,
        # project trust) BESIDE the ~/.claude dir; under a redirected CLAUDE_CONFIG_DIR
        # it is expected at <home>/.claude.json. Seed it too, or Claude Code finds no
        # main config, writes a fresh default and backs it up, and warns once per
        # internal phase (harmless but noisy). Deleted with the run like the rest.
        main_config = Path.home() / ".claude.json"
        if main_config.is_file():
            try:
                shutil.copy2(main_config, config_home / ".claude.json")
            except OSError:
                pass  # best-effort; the run still proceeds without it (just noisy)
        return {"CLAUDE_CONFIG_DIR": str(config_home)}


register(ClaudeAdapter())
