# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Grants (`--grant net`): opening a capability for the launched client.

Enablement, not restriction. A grant is part of the call, so it is part of the
key (a net call gets its own cassette), kept readable and order-independent. It
does not make the call non-cacheable -- choosing the cache is the intent to cache.
"""

from __future__ import annotations

import pytest

from generic_ml_cache.cache import Request
from generic_ml_cache.checksum import checksum_input_data
from generic_ml_cache.cli import main


def _req(**kw) -> Request:
    return Request(client="fake", model="m", effort="high", context="", prompt="p", **kw)


def _key(request: Request) -> str:
    return checksum_input_data(request.input_data)


def test_no_grant_keys_identically_to_empty():
    # Back-compat: no grant, or an empty list, keys exactly as before.
    assert _key(_req()) == _key(_req(grants=[]))


def test_a_grant_changes_the_key():
    assert _key(_req()) != _key(_req(grants=["net"]))


def test_grants_are_order_independent_and_deduped():
    assert _key(_req(grants=["a", "b"])) == _key(_req(grants=["b", "a"]))
    assert _key(_req(grants=["net", "net"])) == _key(_req(grants=["net"]))


def test_grant_is_stored_readably_not_hashed():
    # Unlike client_args (which may carry secrets and is hashed), a grant is
    # non-secret and is kept readable in the keyed input_data.
    assert _req(grants=["net"]).input_data.get("grants") == "net"


_CLI = ["--client", "fake", "--model", "m", "--effort", "high"]


def test_grant_keys_run_and_check_identically(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT p", "--grant", "net"]) == 0
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT p", "--grant", "net"]) == 0
    assert "status  : hit" in capsys.readouterr().out


def test_grant_yields_a_distinct_cassette(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT q", "--grant", "net"]) == 0
    capsys.readouterr()
    # same prompt, no grant -> different key -> miss
    assert main(["check", *_CLI, "--prompt", "STDOUT q"]) == 0
    assert "status  : miss" in capsys.readouterr().out


def test_unknown_grant_is_rejected():
    with pytest.raises(SystemExit):
        main(["run", *_CLI, "--prompt", "STDOUT z", "--grant", "bogus"])


def test_all_five_capabilities_are_accepted_and_key_distinctly():
    # The five-capability vocabulary the adapters implement, each its own cassette.
    caps = ["net", "read", "write", "shell", "web-search"]
    keys = {c: _key(_req(grants=[c])) for c in caps}
    assert len(set(keys.values())) == len(caps)  # all distinct
    assert all(k != _key(_req()) for k in keys.values())  # all differ from no-grant


def test_web_search_grant_runs_via_cli(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT w", "--grant", "web-search"]) == 0
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT w", "--grant", "web-search"]) == 0
    assert "status  : hit" in capsys.readouterr().out
