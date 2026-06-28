# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Exit-code stability tests.

These tests assert the exact integer values of exit codes documented in
docs/reference/cli.md. They serve as a regression guard: if a controller changes
a return value without updating the docs and this file together, CI fails.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from generic_ml_cache_cli.cli import main  # type: ignore[attr-defined]

_GMLCACHE = [sys.executable, "-m", "generic_ml_cache_cli"]


# ---------------------------------------------------------------------------
# Exit 0 — success
# ---------------------------------------------------------------------------


def test_exit_0_on_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_exit_0_on_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_exit_0_config_validate_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "absent.ini"))
    result = main(["config", "validate"])
    assert result == 0


def test_exit_0_check_hit(tmp_path, monkeypatch):
    """check reports 0 on both hit and miss — it is informational only."""
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    result = main(
        [
            "check",
            "--client",
            "claude",
            "--model",
            "claude-sonnet-4-6",
            "--prompt",
            "this prompt is not cached",
        ]
    )
    assert result == 0


# ---------------------------------------------------------------------------
# Exit 2 — usage / validation error
# ---------------------------------------------------------------------------


def test_exit_2_argparse_unknown_flag():
    result = subprocess.run(
        [*_GMLCACHE, "--no-such-flag"],
        capture_output=True,
    )
    assert result.returncode == 2


def test_exit_2_run_missing_required_args():
    result = subprocess.run(
        [*_GMLCACHE, "run"],
        capture_output=True,
    )
    assert result.returncode == 2


def test_exit_2_execution_bare_subcommand(tmp_path, monkeypatch):
    """gmlcache execution with no subcommand prints usage and exits 2."""
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    result = main(["execution"])
    assert result == 2


def test_exit_2_session_start_invalid_spec(tmp_path, monkeypatch):
    """session start --client without --model is an invalid partial spec."""
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    result = main(["session", "start", "--client", "claude"])
    assert result == 2


# ---------------------------------------------------------------------------
# Exit 3 — cache miss in offline mode
# ---------------------------------------------------------------------------


def test_exit_3_run_offline_miss(tmp_path, monkeypatch):
    """run --mode offline on an empty store must exit 3 (CacheMiss)."""
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    result = main(
        [
            "run",
            "--mode",
            "offline",
            "--client",
            "claude",
            "--model",
            "claude-sonnet-4-6",
            "--prompt",
            "prompt that is definitely not cached",
        ]
    )
    assert result == 3


# ---------------------------------------------------------------------------
# Exit 4 — encryption / config error
# ---------------------------------------------------------------------------


def test_exit_4_encrypt_already_encrypted(tmp_path, monkeypatch):
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    main(["encrypt"])
    result = main(["encrypt"])
    assert result == 4


def test_exit_4_config_validate_invalid_value(tmp_path, monkeypatch):
    config = tmp_path / "config.ini"
    config.write_text("[defaults]\nmode = invalid_value\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(config))
    result = main(["config", "validate"])
    assert result == 4
