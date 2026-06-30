# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for the Cursor agent CLI.

Cursor bakes reasoning effort into the model id, so ``effort`` is appended to
the model string. Best-effort for v0.0.1; correct here as needed.
"""

from __future__ import annotations

import json

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.parsed_output import ParsedOutput
from generic_ml_cache_core.application.domain.model.run.client_config import GrantConfigFile
from generic_ml_cache_core.application.domain.model.usage.usage import Usage, int_or_none
from generic_ml_cache_core.application.port.out.client_config_port import ClientConfigPort

from generic_ml_cache_adapters.adapter.out.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.out.client.composed_local_client import ComposedLocalClient
from generic_ml_cache_adapters.adapter.out.client.output_parsing import (
    ensure_trailing_newline,
    final_result_object,
)


class CursorCliAdapter(ComposedLocalClient, ClientConfigPort):
    """Adapter for the Cursor agent CLI. Composes a CliRuntime and supplies only
    Cursor's translation hooks (including its own model-listing)."""

    name = "cursor"
    default_executable = "cursor-agent"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        wire_cli_client(self, executable_override, timeout, stream_path)

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.local_cli(
            "cursor", {ClientCapability.RUN, ClientCapability.LIST_MODELS}, "Cursor Agent"
        )

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
    ) -> list[str]:
        # cursor-agent takes the prompt ONLY as a positional argument -- its CLI has
        # no stdin/file path for the prompt (verified against `cursor-agent --help`:
        # `[prompt...]`, no `-`, no --prompt-file), unlike claude and codex. Feeding
        # the prompt on stdin makes it hang waiting for a positional it never gets.
        # So the prompt stays in argv, which means a cursor prompt is bounded by the
        # OS argument-size limit (~128 KiB/arg on Linux, ~32 KB whole command line on
        # Windows); claude and codex have no such ceiling because they read the
        # prompt from stdin.
        #
        # Current cursor-agent has NO system-prompt flag (removed) and headless
        # --print ignores workspace rule files (.cursor/rules, .cursorrules,
        # AGENTS.md) -- both verified against the live CLI -- so the prime directive
        # (system prompt) and context are folded into the prompt argument itself.
        # None of this enters the Request, so input_data and the cache key are
        # unchanged: cursor keys identically to claude/codex.
        segments = [system_prompt] if system_prompt else []
        if context:
            segments.append(context)
        segments.append(prompt)
        full_prompt = "\n\n".join(segments)
        # Cursor encodes effort in the model id. Pass a full id from --list-models
        # with no effort (preferred), or a base id plus an effort to append. Do not
        # pass both, or the effort is duplicated.
        model_id = f"{model}-{effort}" if effort else model
        # Capability doors (read/write/shell/web-search) now live in
        # $CURSOR_CONFIG_DIR/cli-config.json written by grant_setup. --trust stays
        # here: it is workspace-trust transport (accept the ephemeral run folder),
        # not a capability. The net grant's external-egress flag (--force) is added
        # by grant_argv, because Cursor's sandbox network is not file-addressable
        # headless -- see grant_argv.
        return [
            executable,
            *self.write_access_argv(run_dir),
            "--model",
            model_id,
            "--print",
            # Streaming output (NDJSON) so a live consumer can watch progress; the
            # recorded answer + usage come from the final `result` event, which is
            # identical to the old single-object json (proven against the live CLI),
            # so the stored output is unchanged. The prompt stays the trailing positional.
            "--output-format",
            "stream-json",
            # Passthrough args before the prompt: cursor-agent's prompt is a
            # trailing (variadic) positional, so anything after it is read as prompt
            # text, not a flag. Spliced here verbatim, uninterpreted.
            *client_args,
            full_prompt,
        ]

    def parse_output(self, stdout: str) -> ParsedOutput:
        """Cursor's ``--output-format json`` is a single object: ``result`` is the
        answer text and ``usage`` (camelCase keys) holds the token counts. Cursor
        reports input/output and both cache directions, but no reasoning split and
        no cost.
        """
        try:
            doc = final_result_object(stdout)
            if not isinstance(doc, dict):
                raise ValueError("no result object")
        except (json.JSONDecodeError, ValueError):
            return ParsedOutput(text=stdout, usage=None)

        text = doc.get("result")
        if not isinstance(text, str):
            return ParsedOutput(text=stdout, usage=None)

        block = doc.get("usage") if isinstance(doc.get("usage"), dict) else None
        usage = None
        if block is not None:
            usage = Usage(
                input_tokens=int_or_none(block.get("inputTokens")),
                output_tokens=int_or_none(block.get("outputTokens")),
                cache_read_tokens=int_or_none(block.get("cacheReadTokens")),
                cache_write_tokens=int_or_none(block.get("cacheWriteTokens")),
                reasoning_tokens=None,
                cost_usd=None,
                raw=dict(block),
            )
        return ParsedOutput(text=ensure_trailing_newline(text), usage=usage)

    def write_access_argv(self, run_dir):
        # cursor-agent refuses an untrusted workspace ("Workspace Trust Required")
        # in the isolated run folder. --trust accepts it; in --print mode the agent
        # already has its write tool, so trust alone is sufficient to write (the
        # separate --force is not needed). Reads outside the folder are unaffected.
        # Verified against cursor-agent --print on the live CLI.
        return ["--trust"]

    def build_grants_config_file(self, grants):
        # Uniform door: $CURSOR_CONFIG_DIR/cli-config.json so the FILE enables
        # capabilities. The project-level permission file was stripped by a security
        # fix (GHSA-v64q-396f-7m79), so we redirect the config home instead. Write
        # is always on (the record-path guarantee). Cursor has no file-level read
        # *deny* headless -- a documented limit, not a door we close. Cursor folds
        # web search into fetch, so web-search maps to WebFetch. net needs the shell
        # (to reach the network) plus fetch; its external egress is opened by
        # grant_argv. The cache enables (docs/reference/grants.md).
        allow = ["Write(**)"]
        if "read" in grants:
            allow.append("Read(**)")
        if "shell" in grants or "net" in grants:
            allow.append("Shell(**)")
        if "net" in grants or "web-search" in grants:
            allow.append("WebFetch(**)")
        # de-dup, preserve order
        seen, ordered = set(), []
        for tok in allow:
            if tok not in seen:
                seen.add(tok)
                ordered.append(tok)
        config = {"version": 1, "permissions": {"allow": ordered}}
        return GrantConfigFile(
            file_name="cli-config.json", content=json.dumps(config).encode("utf-8")
        )

    def get_token_files(self):
        return []  # Cursor seeds no credentials into its config home

    def config_home_env_var(self):
        return "CURSOR_CONFIG_DIR"

    def stdin_payload(self, context, prompt, system_prompt):
        # cursor-agent has no stdin prompt path; the prompt rides as the trailing
        # argv positional (see build_argv), so nothing is delivered on stdin.
        return None

    def grant_argv(self, grants):
        # Cursor's sandbox blocks external network egress and its sandbox.json
        # networkPolicy is IGNORED under headless --print (upstream bug), so the
        # file cannot open the network. The verified headless egress lever is
        # --force ("Force allow commands unless explicitly denied"; --yolo is its
        # alias). So net = the file's Shell/WebFetch allow PLUS this forced flag.
        # Transport forced by the client, not a capability door (docs/reference/grants.md).
        return ["--force"] if "net" in grants else []

    def models_argv(self, executable: str) -> list[str] | None:
        return [executable, "--list-models"]

    def parse_model_list(self, stdout: str) -> list[ModelInfo]:
        """Parse ``cursor-agent --list-models`` output.

        Each model is one ``<id> - <Label>`` line. A header line and a trailing
        ``Tip:`` line are ignored; a ``(default)``/``(current)`` marker on the
        label is lifted into a flag. The id is taken verbatim -- it is exactly
        what a caller passes to ``--model``.
        """
        models: list[ModelInfo] = []
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

    def stream_event(self, raw_line):
        try:
            d = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return {"kind": "start"}
        if t == "assistant":
            return {"kind": "message"}
        if t == "result":
            return {"kind": "result"}
        return None


# Backward-compatible alias.
CursorAdapter = CursorCliAdapter
