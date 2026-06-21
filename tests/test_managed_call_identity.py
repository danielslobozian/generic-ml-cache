# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ManagedCallIdentity and generate_key()."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.managed_call_identity import ManagedCallIdentity


def test_abstract_call_identity_cannot_be_instantiated():
    from generic_ml_cache.application.domain.model.call_identity import CallIdentity

    with pytest.raises(TypeError):
        CallIdentity()  # type: ignore[abstract]


def test_managed_identity_is_a_call_identity():
    from generic_ml_cache.application.domain.model.call_identity import CallIdentity

    assert isinstance(_make_identity(), CallIdentity)


def _make_identity(**overrides) -> ManagedCallIdentity:
    defaults = dict(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx_sha256",
        prompt_fingerprint="prompt_sha256",
    )
    defaults.update(overrides)
    return ManagedCallIdentity(**defaults)


def test_generate_key_returns_hex_string():
    identity = _make_identity()
    key = identity.generate_key()
    assert isinstance(key, str)
    assert len(key) == 64
    assert all(char in "0123456789abcdef" for char in key)


def test_generate_key_is_deterministic():
    identity = _make_identity()
    assert identity.generate_key() == identity.generate_key()


def test_different_clients_produce_different_keys():
    assert _make_identity(client="claude").generate_key() != _make_identity(client="codex").generate_key()


def test_different_models_produce_different_keys():
    assert _make_identity(model="sonnet").generate_key() != _make_identity(model="haiku").generate_key()


def test_different_effort_produces_different_keys():
    assert _make_identity(effort="high").generate_key() != _make_identity(effort="low").generate_key()


def test_different_context_fingerprint_produces_different_keys():
    assert _make_identity(context_fingerprint="aaa").generate_key() != _make_identity(context_fingerprint="bbb").generate_key()


def test_different_prompt_fingerprint_produces_different_keys():
    assert _make_identity(prompt_fingerprint="aaa").generate_key() != _make_identity(prompt_fingerprint="bbb").generate_key()


def test_different_input_files_produce_different_keys():
    without_files = _make_identity()
    with_file = _make_identity(input_file_fingerprints={"/src/a.py": "sha_a"})
    assert without_files.generate_key() != with_file.generate_key()


def test_grants_are_order_independent():
    with_net_first = _make_identity(grants=frozenset({"net", "read"}))
    with_read_first = _make_identity(grants=frozenset({"read", "net"}))
    assert with_net_first.generate_key() == with_read_first.generate_key()


def test_different_grants_produce_different_keys():
    with_net = _make_identity(grants=frozenset({"net"}))
    with_read = _make_identity(grants=frozenset({"read"}))
    assert with_net.generate_key() != with_read.generate_key()


def test_empty_grants_matches_no_grants():
    no_grants = _make_identity()
    empty_grants = _make_identity(grants=frozenset())
    assert no_grants.generate_key() == empty_grants.generate_key()


def test_client_args_fingerprint_enters_key():
    without_args = _make_identity()
    with_args = _make_identity(client_args_fingerprint="args_sha256")
    assert without_args.generate_key() != with_args.generate_key()


def test_is_frozen():
    identity = _make_identity()
    with pytest.raises(Exception):
        identity.client = "codex"  # type: ignore[misc]


def test_allow_paths_are_not_a_field():
    assert not hasattr(ManagedCallIdentity, "allow_paths")
