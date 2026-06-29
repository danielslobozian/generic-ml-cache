# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared build_call_identity helper."""

from __future__ import annotations

from typing import List

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.usecase.call_identity_building import build_call_identity
from generic_ml_cache_core.common.checksum import text_checksum


class FakeFingerprint(FileFingerprintPort):
    def __init__(self) -> None:
        self.fingerprinted: List[str] = []

    def fingerprint(self, path: str) -> str:
        self.fingerprinted.append(path)
        return "fp_" + path


def _command(**overrides) -> RunMlExecutionCommand:
    base = dict(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="claude",
        model="sonnet",
        effort="high",
        context="ctx",
        prompt="do it",
    )
    base.update(overrides)
    return RunMlExecutionCommand(**base)


def test_copies_the_scalar_key_fields():
    identity = build_call_identity(FakeFingerprint(), _command())
    assert identity.client == "claude"
    assert identity.model == "sonnet"
    assert identity.effort == "high"


def test_fingerprints_context_and_prompt_as_text():
    identity = build_call_identity(FakeFingerprint(), _command(context="ctx", prompt="p"))
    assert identity.context_fingerprint == text_checksum("ctx")
    assert identity.prompt_fingerprint == text_checksum("p")


def test_input_files_are_fingerprinted_through_the_port():
    fingerprint = FakeFingerprint()
    identity = build_call_identity(fingerprint, _command(input_file_paths=["/a", "/b"]))
    assert fingerprint.fingerprinted == ["/a", "/b"]
    assert identity.input_file_fingerprints == {"/a": "fp_/a", "/b": "fp_/b"}


def test_client_args_fingerprint_is_none_when_absent():
    identity = build_call_identity(FakeFingerprint(), _command())
    assert identity.client_args_fingerprint is None


def test_client_args_fingerprint_is_set_when_present():
    identity = build_call_identity(FakeFingerprint(), _command(client_args=["--flag"]))
    assert identity.client_args_fingerprint is not None


def test_grants_become_a_frozenset():
    identity = build_call_identity(FakeFingerprint(), _command(grants=["net", "read"]))
    assert identity.grants == frozenset({"net", "read"})


def test_user_system_prompt_is_fingerprinted_into_the_identity():
    with_sys = build_call_identity(FakeFingerprint(), _command(user_system_prompt="be terse"))
    without = build_call_identity(FakeFingerprint(), _command())
    assert with_sys.system_fingerprint is not None
    assert without.system_fingerprint is None
    assert with_sys.generate_key() != without.generate_key()


def test_key_is_deterministic():
    first = build_call_identity(FakeFingerprint(), _command()).generate_key()
    second = build_call_identity(FakeFingerprint(), _command()).generate_key()
    assert first == second
