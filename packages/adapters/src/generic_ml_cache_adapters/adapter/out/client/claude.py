# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.parsed_output import ParsedOutput
from generic_ml_cache_core.application.domain.model.run.client_config import (
    CredentialFile,
    GrantConfigFile,
)
from generic_ml_cache_core.application.domain.model.usage.usage import (
    Usage,
    float_or_none,
    int_or_none,
)

from generic_ml_cache_adapters.adapter.out.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.out.client.output_parsing import (
    ensure_trailing_newline,
    final_result_object,
)
from generic_ml_cache_adapters.discovery.descriptors import local_cli_descriptor


class ClaudeCliAdapter:
    """Adapter for Anthropic's Claude Code CLI. A pure translator: it composes a
    CliRuntime (the shared call engine) and supplies only Claude's hooks."""

    name = "claude"
    default_executable = "claude"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        wire_cli_client(self, executable_override, timeout, stream_path)

    @classmethod
    def descriptor(cls):
        return local_cli_descriptor("claude", {ClientCapability.RUN}, "Claude Code")

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
        # Streaming output mode (one NDJSON event per line) so a live consumer can
        # watch progress; the recorded answer + usage are lifted from the final
        # `result` event, which is byte-identical to the old single-object json
        # (proven against the live CLI), so the stored output is unchanged. --verbose is
        # required for stream-json to emit the full stream; --include-partial-
        # messages adds token-level deltas for the live feed.
        argv += [
            "--append-system-prompt",
            system_prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
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
            doc = final_result_object(stdout)
            if not isinstance(doc, dict):
                raise ValueError("no result object")
        except (json.JSONDecodeError, ValueError):
            return ParsedOutput(text=stdout, usage=None)

        text = doc.get("result")
        if not isinstance(text, str):
            # Not the shape we expected -- keep the raw output, skip usage.
            return ParsedOutput(text=stdout, usage=None)

        _usage_val = doc.get("usage")
        block: Dict[str, Any] = _usage_val if isinstance(_usage_val, dict) else {}
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
        return ParsedOutput(text=ensure_trailing_newline(text), usage=usage)

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

    def build_grants_config_file(self, grants):
        # Uniform door: settings.json in a redirected CLAUDE_CONFIG_DIR so the FILE
        # (not a flag) enables capabilities. Verified against the live CLI: the
        # redirected home governs because the run folder is clean of a project
        # .claude/ that would outrank it. acceptEdits + Write/Edit are always on so
        # a file-producing call actually writes (the record-path guarantee); each
        # named grant ADDS its allow-token. The cache enables; it never closes
        # (docs/reference/grants.md).
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
        return GrantConfigFile(
            file_name="settings.json", content=json.dumps(settings).encode("utf-8")
        )

    def get_token_files(self):
        # Seed credentials so the relocated home is authenticated. Subscription
        # login lives in ~/.claude; an API key in the env carries over on its own.
        # Bulk caches (projects/history/todos/shell-snapshots) are skipped; a stray
        # settings.local.json would outrank ours, so it is dropped.
        creds = []
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
                creds.append(CredentialFile(source=child, target_name=child.name))
        # Claude Code also keeps a top-level ~/.claude.json (account, onboarding,
        # project trust) BESIDE the ~/.claude dir; under a redirected CLAUDE_CONFIG_DIR
        # it is expected at <home>/.claude.json. Seed it too, or Claude Code finds no
        # main config, writes a fresh default and backs it up, and warns once per
        # internal phase (harmless but noisy). Deleted with the run like the rest.
        main_config = Path.home() / ".claude.json"
        if main_config.is_file():
            creds.append(CredentialFile(source=main_config, target_name=".claude.json"))
        return creds

    def config_home_env_var(self):
        return "CLAUDE_CONFIG_DIR"

    def stream_event(self, raw_line):
        try:
            d = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        t = d.get("type")
        if t == "system":
            sub = d.get("subtype")
            if sub == "init":
                return {"kind": "start"}
            if sub == "thinking_tokens":
                return {"kind": "thinking"}
            return None
        if t == "stream_event":
            ev = d.get("event")
            if isinstance(ev, dict) and ev.get("type") == "content_block_start":
                block = ev.get("content_block")
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    return {"kind": "tool", "name": block.get("name")}
            return None
        if t == "result":
            return {"kind": "result"}
        return None


# Backward-compatible alias — existing imports of ClaudeAdapter keep working.
ClaudeAdapter = ClaudeCliAdapter
