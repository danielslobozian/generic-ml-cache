# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ProbeCommand."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.application.port.inbound.probe_command import ProbeCommand


def _command(**overrides) -> ProbeCommand:
    base = dict(client="claude", model="sonnet", effort="high", context="ctx", prompt="do it")
    base.update(overrides)
    return ProbeCommand(**base)


def test_defaults():
    command = _command()
    assert command.input_file_paths == []
    assert command.allow_paths == []
    assert command.scan_trust is False
    assert command.client_args == []
    assert command.grants == []


def test_plain_call_is_cacheable():
    assert _command().is_uncacheable is False


def test_allow_paths_make_it_uncacheable():
    assert _command(allow_paths=["/workspace"]).is_uncacheable is True


def test_scan_trust_makes_it_cacheable_again():
    assert _command(allow_paths=["/workspace"], scan_trust=True).is_uncacheable is False


def test_carries_no_run_policy():
    assert not hasattr(ProbeCommand, "cache_mode")
    assert not hasattr(ProbeCommand, "persist_output")
    assert not hasattr(ProbeCommand, "record_on_error")


def test_is_frozen():
    command = _command()
    with pytest.raises(Exception):
        command.prompt = "other"  # type: ignore[misc]
