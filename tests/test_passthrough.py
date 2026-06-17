# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Passthrough client arguments (`--client-arg`).

Extra raw args appended verbatim to the client launch. They are part of the key
(different args = different call = own cassette), but only their *fingerprint* is
keyed, so the raw strings -- which may hold secrets -- never reach a cassette.
"""

from __future__ import annotations

from generic_ml_cache.cache import Request
from generic_ml_cache.checksum import checksum_input_data


def _req(**kw) -> Request:
    return Request(client="fake", model="m", effort="high", context="", prompt="p", **kw)


def _key(request: Request) -> str:
    return checksum_input_data(request.input_data)


def test_empty_passthrough_keys_identically_to_none():
    # Back-compat: no args, or an empty list, must key exactly as before.
    assert _req().input_data == _req(client_args=[]).input_data
    assert _key(_req()) == _key(_req(client_args=[]))


def test_passthrough_args_change_the_key():
    assert _key(_req()) != _key(_req(client_args=["--thinking", "high"]))


def test_same_args_in_same_order_share_a_key():
    assert _key(_req(client_args=["--a", "1"])) == _key(_req(client_args=["--a", "1"]))


def test_arg_order_is_significant():
    # CLI flags are positional, so a different order is a different invocation.
    assert _key(_req(client_args=["--a", "--b"])) != _key(_req(client_args=["--b", "--a"]))


def test_raw_args_never_appear_in_the_keyed_data():
    secret = "--token=SUPERSECRET"
    data = _req(client_args=[secret]).input_data

    # The raw secret appears nowhere -- not as a value, not inside a key.
    assert secret not in data.values()
    assert all(secret not in k for k in data)

    # Only a single fingerprint entry, whose key suffix and value are the digest.
    arg_keys = [k for k in data if k.startswith("client_args:")]
    assert len(arg_keys) == 1
    digest = arg_keys[0].split(":", 1)[1]
    assert len(digest) == 64
    assert data[arg_keys[0]] == digest
    assert "SUPERSECRET" not in digest
