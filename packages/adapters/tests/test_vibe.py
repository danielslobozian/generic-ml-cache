# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for VibeCliAdapter — Mistral's Vibe CLI (model via env, prompt via argv)."""

from __future__ import annotations

import json
from pathlib import Path

from generic_ml_cache_bootstrap.discovery.composition import registered_names
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)

from generic_ml_cache_adapters.adapter.outbound.client.prime_directive import PRIME_DIRECTIVE
from generic_ml_cache_adapters.adapter.outbound.client.vibe import VibeCliAdapter

# The shape Vibe's `--output json` returns: a JSON array of message objects; the answer is
# the final assistant message's content. (Trimmed system content — the real one is huge.)
_VIBE_JSON = json.dumps(
    [
        {"role": "system", "content": "You are Mistral Vibe."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "VIBE_OK", "reasoning_content": None},
    ]
)


def _argv(tmp_path: Path, **overrides) -> list[str]:
    base = {
        "executable": "/usr/bin/vibe",
        "run_dir": tmp_path,
        "model": "mistral-medium-3.5",
        "effort": "",
        "context": "CTX",
        "prompt": "PROMPT",
        "system_prompt": PRIME_DIRECTIVE,
    }
    base.update(overrides)
    return VibeCliAdapter().build_argv(**base)


class TestBuildArgv:
    def test_prompt_and_flags(self, tmp_path):
        argv = _argv(tmp_path)
        assert argv[0] == "/usr/bin/vibe"
        assert argv[1] == "-p"
        # prime directive + context + prompt fold into the -p argument
        assert "PROMPT" in argv[2] and "CTX" in argv[2] and PRIME_DIRECTIVE in argv[2]
        assert "--output" in argv and "json" in argv
        assert "--yolo" in argv  # approve tools non-interactively
        assert "--trust" in argv  # accept the ephemeral run folder
        assert argv[argv.index("--workdir") + 1] == str(tmp_path)

    def test_model_and_effort_not_in_argv(self, tmp_path):
        # Vibe takes neither on the command line: model rides in extra_run_env, effort
        # (thinking) is config-only. So the model/effort values must not leak into argv.
        argv = _argv(tmp_path, model="mistral-medium-3.5", effort="high")
        assert "--model" not in argv
        assert "mistral-medium-3.5" not in argv  # not as a standalone arg
        assert "--effort" not in argv and "high" not in argv

    def test_passthrough_args_appended(self, tmp_path):
        argv = _argv(tmp_path, client_args=["--max-turns", "3"])
        assert argv[-2:] == ["--max-turns", "3"]


class TestExtraRunEnv:
    def test_model_becomes_vibe_active_model(self):
        env = VibeCliAdapter().extra_run_env("mistral-medium-3.5", "")
        assert env["VIBE_ACTIVE_MODEL"] == "mistral-medium-3.5"

    def test_empty_model_omits_the_override(self):
        env = VibeCliAdapter().extra_run_env("", "")
        assert "VIBE_ACTIVE_MODEL" not in env

    def test_incidental_network_is_disabled(self):
        env = VibeCliAdapter().extra_run_env("m", "")
        assert env["VIBE_ENABLE_TELEMETRY"] == "false"
        assert env["VIBE_ENABLE_UPDATE_CHECKS"] == "false"
        assert env["VIBE_ENABLE_NOTIFICATIONS"] == "false"


class TestParseOutput:
    def test_takes_the_final_assistant_content(self):
        parsed = VibeCliAdapter().parse_output(_VIBE_JSON)
        assert parsed.text == "VIBE_OK\n"  # trailing newline normalised
        assert parsed.usage is None  # Vibe's json output carries no usage

    def test_last_assistant_wins(self):
        body = json.dumps(
            [
                {"role": "assistant", "content": "first"},
                {"role": "user", "content": "again"},
                {"role": "assistant", "content": "final"},
            ]
        )
        assert VibeCliAdapter().parse_output(body).text == "final\n"

    def test_malformed_json_returns_raw_no_usage(self):
        parsed = VibeCliAdapter().parse_output("not json at all")
        assert parsed.text == "not json at all"
        assert parsed.usage is None

    def test_no_assistant_message_returns_raw(self):
        body = json.dumps([{"role": "user", "content": "hi"}])
        assert VibeCliAdapter().parse_output(body).text == body


class TestContract:
    def test_stdin_payload_is_none(self):
        # No stdin path; the prompt rides in argv.
        assert VibeCliAdapter().stdin_payload("CTX", "PROMPT", "SYS") is None

    def test_descriptor(self):
        desc = VibeCliAdapter.descriptor()
        assert desc.client_name == "vibe"
        assert ClientCapability.RUN in desc.capabilities
        assert ClientCapability.LIST_MODELS not in desc.capabilities

    def test_registered_via_entry_point(self):
        # Discovered through the gmlcache.adapters entry point (needs the package
        # reinstalled after adding it — the nox gate's uv sync does that).
        assert "vibe" in registered_names()
