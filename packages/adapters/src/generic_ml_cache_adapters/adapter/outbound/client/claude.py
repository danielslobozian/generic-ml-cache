# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Anthropic's Claude Code CLI (headless / print mode).

Treat the exact flags as configuration, not gospel -- override the executable
with the seam and adjust here if the CLI changes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
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
from generic_ml_cache_core.application.port.outbound.client_config_port import ClientConfigPort

from generic_ml_cache_adapters.adapter.outbound.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.outbound.client.composed_local_client import (
    ComposedLocalClient,
)
from generic_ml_cache_adapters.adapter.outbound.client.output_parsing import (
    ensure_trailing_newline,
    final_result_object,
    is_json_object,
)


class ClaudeCliAdapter(ComposedLocalClient, ClientConfigPort):
    """Adapter for Anthropic's Claude Code CLI. A pure translator: it composes a
    CliRuntime (the shared call engine) and supplies only Claude's hooks."""

    name = "claude"
    default_executable = "claude"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(
        self,
        executable_override: str | None = None,
        timeout: float | None = None,
        stream_path: str | None = None,
    ) -> None:
        wire_cli_client(self, executable_override, timeout, stream_path)

    @classmethod
    def descriptor(cls) -> AdapterDescriptor:
        return AdapterDescriptor.local_cli("claude", {ClientCapability.RUN}, "Claude Code")

    def build_argv(
        self,
        executable: str,
        run_dir: Path,
        model: str,
        effort: str,
        context: str,
        prompt: str,
        system_prompt: str,
        client_args: Sequence[str] = (),
        grants: Sequence[str] = (),
    ) -> list[str]:
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

        usage_value = doc.get("usage")
        usage_block: dict[str, Any] = usage_value if is_json_object(usage_value) else {}
        raw: dict[str, Any] = {}
        for key in ("usage", "modelUsage", "total_cost_usd"):
            if key in doc:
                raw[key] = doc[key]

        usage = Usage(
            input_tokens=int_or_none(usage_block.get("input_tokens")),
            output_tokens=int_or_none(usage_block.get("output_tokens")),
            cache_read_tokens=int_or_none(usage_block.get("cache_read_input_tokens")),
            cache_write_tokens=int_or_none(usage_block.get("cache_creation_input_tokens")),
            # Claude folds reasoning into output_tokens; it is not separable here.
            reasoning_tokens=None,
            cost_usd=float_or_none(doc.get("total_cost_usd")),
            raw=raw,
        )
        return ParsedOutput(text=ensure_trailing_newline(text), usage=usage)

    def stdin_payload(self, context: str, prompt: str, system_prompt: str) -> str | None:
        # Prompt + context go to the client on stdin. The system prompt is a
        # separate, small argv flag (--append-system-prompt), so it stays in argv.
        return f"{context}\n\n{prompt}" if context else prompt

    def read_access_argv(self, paths: Sequence[str]) -> list[str]:
        # Claude Code grants read access to extra directories via --add-dir.
        argv: list[str] = []
        for readable_path in paths:
            argv += ["--add-dir", readable_path]
        return argv

    def build_grants_config_file(self, grants: Sequence[str]) -> GrantConfigFile:
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

    def get_token_files(self) -> list[CredentialFile]:
        # Seed credentials so the relocated home is authenticated. Subscription
        # login lives in ~/.claude; an API key in the env carries over on its own.
        # Bulk caches (projects/history/todos/shell-snapshots) are skipped; a stray
        # settings.local.json would outrank ours, so it is dropped.
        credential_files: list[CredentialFile] = []
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
                credential_files.append(CredentialFile(source=child, target_name=child.name))
        # Claude Code also keeps a top-level ~/.claude.json (account, onboarding,
        # project trust) BESIDE the ~/.claude dir; under a redirected CLAUDE_CONFIG_DIR
        # it is expected at <home>/.claude.json. Seed it too, or Claude Code finds no
        # main config, writes a fresh default and backs it up, and warns once per
        # internal phase (harmless but noisy). Deleted with the run like the rest.
        main_config = Path.home() / ".claude.json"
        if main_config.is_file():
            credential_files.append(CredentialFile(source=main_config, target_name=".claude.json"))
        return credential_files

    def config_home_env_var(self) -> str:
        return "CLAUDE_CONFIG_DIR"

    def stream_event(self, raw_line: str) -> dict[str, str | None] | None:
        try:
            line_event = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        if not is_json_object(line_event):
            return None
        event_type = line_event.get("type")
        if event_type == "system":
            subtype = line_event.get("subtype")
            if subtype == "init":
                return {"kind": "start"}
            if subtype == "thinking_tokens":
                return {"kind": "thinking"}
            return None
        if event_type == "stream_event":
            inner_event = line_event.get("event")
            if is_json_object(inner_event) and inner_event.get("type") == "content_block_start":
                content_block = inner_event.get("content_block")
                if is_json_object(content_block) and content_block.get("type") == "tool_use":
                    return {"kind": "tool", "name": content_block.get("name")}
            return None
        if event_type == "result":
            return {"kind": "result"}
        return None


# Backward-compatible alias — existing imports of ClaudeAdapter keep working.
ClaudeAdapter = ClaudeCliAdapter
