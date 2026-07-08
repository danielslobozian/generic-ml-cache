# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter for Mistral's Vibe CLI (non-interactive / programmatic mode).

Vibe differs from the other CLI clients in two ways, both verified against the live
CLI (v2.19.0):

* **Model is not an argv flag.** Vibe selects the model via ``active_model`` config,
  overridable by the top-level ``VIBE_ACTIVE_MODEL`` env var (Vibe's config layer is
  pydantic-settings with ``env_prefix="VIBE_"``). So the model rides in ``extra_run_env``,
  not ``build_argv``.
* **Effort has no per-call lever.** Vibe's effort analog is ``thinking``, a field nested
  inside the ``[[models]]`` list -- unreachable by env (a list element cannot be indexed
  through ``env_nested_delimiter``) and exposed by no flag. v1 therefore leaves ``thinking``
  at the model's own default; mapping ``effort -> thinking`` needs a written config home
  and is a follow-up.

Like ``cursor-agent``, Vibe takes the prompt as an argv argument (it has no stdin path --
``vibe -p`` with piped stdin errors "No prompt provided"), so the prompt is bounded by the
OS argument-size limit. Auth comes from the user's ``~/.vibe`` (``.env`` / config), used
directly -- no config-home redirect in v1.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.parsed_output import ParsedOutput

from generic_ml_cache_adapters.adapter.outbound.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.outbound.client.composed_local_client import (
    ComposedLocalClient,
)
from generic_ml_cache_adapters.adapter.outbound.client.output_parsing import (
    ensure_trailing_newline,
    is_json_object,
)


class VibeCliAdapter(ComposedLocalClient):
    """Adapter for Mistral's Vibe CLI. Composes a CliRuntime and supplies only Vibe's
    translation hooks. No config home in v1: the model is an env override, grants/trust
    are argv flags, and auth is read from the user's ``~/.vibe``."""

    name = "vibe"
    default_executable = "vibe"
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
        # RUN only: the Vibe CLI has no model-listing command (models are config
        # entries); listing Mistral models belongs to the Mistral API adapter.
        return AdapterDescriptor.local_cli("vibe", {ClientCapability.RUN}, "Mistral Vibe")

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
        # Vibe has no custom-system-prompt flag, so the prime directive + context fold
        # into the prompt argument -- exactly as cursor-agent does -- and still enter the
        # cache key identically to claude/codex (none of this touches the Request). Model
        # is omitted here on purpose: it rides as VIBE_ACTIVE_MODEL (see extra_run_env).
        # Effort is omitted too -- thinking is config-only (v1 uses the model default).
        segments: list[str] = [system_prompt] if system_prompt else []
        if context:
            segments.append(context)
        segments.append(prompt)
        full_prompt = "\n\n".join(segments)
        return [
            executable,
            "-p",
            full_prompt,
            "--output",
            "json",
            # Non-interactive doors: --yolo approves tool calls without prompting, --trust
            # accepts the ephemeral (untrusted) run folder. --workdir fences Vibe to it.
            "--yolo",
            "--trust",
            "--workdir",
            str(run_dir),
            # Passthrough args last: appended verbatim, uninterpreted.
            *client_args,
        ]

    def extra_run_env(self, model: str, effort: str) -> dict[str, str]:
        # Model selection: VIBE_ACTIVE_MODEL is the top-level config override (env works,
        # unlike the nested `thinking`). Telemetry / update-checks / notifications are
        # turned off so a cached run makes no incidental network calls and stays quiet;
        # unknown VIBE_* vars are ignored by Vibe, so these are safe best-effort.
        env: dict[str, str] = {
            "VIBE_ENABLE_TELEMETRY": "false",
            "VIBE_ENABLE_UPDATE_CHECKS": "false",
            "VIBE_ENABLE_NOTIFICATIONS": "false",
        }
        if model:
            env["VIBE_ACTIVE_MODEL"] = model
        return env

    def stdin_payload(self, context: str, prompt: str, system_prompt: str) -> str | None:
        # No stdin prompt path (verified: `vibe -p` with piped stdin errors "No prompt
        # provided"); the prompt rides as the -p argv argument (see build_argv).
        return None

    def parse_output(self, stdout: str) -> ParsedOutput:
        """Vibe's ``--output json`` is a JSON *array* of message objects; the answer is
        the ``content`` of the final ``assistant`` message. Token usage is not exposed in
        this output, so it stays unknown (never zero)."""
        try:
            messages: Any = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return ParsedOutput(text=stdout, usage=None)
        if not isinstance(messages, list):
            return ParsedOutput(text=stdout, usage=None)
        answer: str | None = None
        for message in cast("list[Any]", messages):
            if is_json_object(message) and message.get("role") == "assistant":
                content = message.get("content")
                if isinstance(content, str):
                    answer = content  # keep the latest; the final one is the answer
        if answer is None:
            # Never found an assistant message -- hand back the raw stream, no usage.
            return ParsedOutput(text=stdout, usage=None)
        return ParsedOutput(text=ensure_trailing_newline(answer), usage=None)
