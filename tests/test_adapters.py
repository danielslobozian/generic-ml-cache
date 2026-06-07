# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys

import pytest

from generic_ml_cache import UnknownClient, get_adapter
from generic_ml_cache.adapters.registry import registered_names
from generic_ml_cache.errors import ClientNotFound
from generic_ml_cache.prime_directive import PRIME_DIRECTIVE


def test_builtins_are_registered():
    for name in ("claude", "codex", "cursor"):
        assert name in registered_names()


def test_unknown_client_raises():
    with pytest.raises(UnknownClient):
        get_adapter("does-not-exist")


@pytest.mark.parametrize("client", ["claude", "codex", "cursor"])
def test_build_argv_includes_model_and_inputs(client, tmp_path):
    adapter = get_adapter(client)
    argv = adapter.build_argv(
        executable="/usr/bin/" + client,
        run_dir=tmp_path,
        model="m-x",
        effort="high",
        context="CTX",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    assert argv[0].endswith(client)
    joined = " ".join(argv)
    assert "m-x" in joined  # the model id appears somewhere
    assert "PROMPT" in joined  # the prompt is delivered
    # effort surfaces somehow (a flag value, a config kv, or baked into model id)
    assert any("high" in a for a in argv)


def test_resolve_executable_honors_explicit_path(tmp_path):
    adapter = get_adapter("claude")
    fake = tmp_path / "claude-bin"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    assert adapter.resolve_executable(str(fake)) == str(fake)


def test_resolve_executable_missing_path_raises():
    adapter = get_adapter("claude")
    with pytest.raises(ClientNotFound):
        adapter.resolve_executable("/no/such/dir/claude")


def test_resolve_executable_found_on_path():
    adapter = get_adapter("claude")
    # Pass a bare name (no separator) that exists on PATH -> exercises the
    # shutil.which branch without mutating the shared adapter.
    name = "python" if sys.platform == "win32" else "sh"
    path = adapter.resolve_executable(name)
    assert path


def test_unknown_executable_name_raises():
    adapter = get_adapter("claude")  # default_executable "claude" not installed
    with pytest.raises(ClientNotFound):
        adapter.resolve_executable("definitely-not-a-real-binary-xyz")
