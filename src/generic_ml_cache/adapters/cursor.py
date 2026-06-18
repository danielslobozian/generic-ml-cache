# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for the Cursor agent CLI.

Cursor bakes reasoning effort into the model id, so ``effort`` is appended to
the model string. Best-effort for v0.0.1; correct here as needed.
"""

from __future__ import annotations

import json
from typing import List, Optional

from ..usage import ParsedOutput, Usage, int_or_none
from .base import ClientAdapter, ModelInfo


class CursorAdapter(ClientAdapter):
    name = "cursor"
    default_executable = "cursor-agent"

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
        net = self.network_access_argv() if "net" in grants else []
        return [
            executable,
            *self.write_access_argv(run_dir),
            *net,
            "--model",
            model_id,
            "--print",
            # JSON output so the call also returns its usage; parse_output lifts
            # the answer text back out. The prompt stays the trailing positional.
            "--output-format",
            "json",
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
            doc = json.loads(stdout)
            if not isinstance(doc, dict):
                raise ValueError("expected a JSON object")
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
        return ParsedOutput(text=text, usage=usage)

    def write_access_argv(self, run_dir):
        # cursor-agent refuses an untrusted workspace ("Workspace Trust Required")
        # in the isolated run folder. --trust accepts it; in --print mode the agent
        # already has its write tool, so trust alone is sufficient to write (the
        # separate --force is not needed). Reads outside the folder are unaffected.
        # Verified against cursor-agent --print on the live CLI.
        return ["--trust"]

    def network_access_argv(self):
        # cursor-agent's sandbox blocks the network by default, and --trust alone
        # (the write door) does NOT open it. The headless flag that does is --force
        # ("Force allow commands unless explicitly denied"; --yolo is just its
        # alias). Verified against the live cursor-agent: --trust alone is blocked,
        # --trust --force reaches an external fetch. (Its sandbox.json networkPolicy
        # is ignored under headless -p -- an upstream bug -- so we don't rely on it.)
        # The cache enables, never restricts (docs/grants.md).
        return ["--force"]

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
