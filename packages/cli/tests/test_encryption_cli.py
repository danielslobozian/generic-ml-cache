# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI tests for encrypt / decrypt / rotate / invalidate."""

from __future__ import annotations

import pytest

pytest.importorskip("cryptography")

from generic_ml_cache_cli.cli import main  # noqa: E402

_RUN = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]


def _token_from(out: str) -> str:
    """The token is printed on its own indented, space-free line."""
    for line in out.splitlines():
        s = line.strip()
        if s and " " not in s and len(s) >= 20:
            return s
    raise AssertionError(f"no token found in:\n{out}")


def _enable(capsys) -> str:
    assert main(["encrypt"]) == 0
    return _token_from(capsys.readouterr().out)


def test_encrypt_then_run_with_token_round_trips(capsys, monkeypatch):
    token = _enable(capsys)
    monkeypatch.setenv("GMLCACHE_TOKEN", token)

    assert main(_RUN + ["--prompt", "STDOUT SECRETMARKER"]) == 0
    assert "SECRETMARKER" in capsys.readouterr().out
    # offline replay against the encrypted store, with the token
    assert main(_RUN + ["--prompt", "STDOUT SECRETMARKER", "--offline"]) == 0
    capsys.readouterr()

    assert main(["status"]) == 0
    assert "encryption  : encrypted" in capsys.readouterr().out


def test_run_without_token_on_encrypted_store_is_blocked(capsys, monkeypatch):
    token = _enable(capsys)
    monkeypatch.setenv("GMLCACHE_TOKEN", token)
    main(_RUN + ["--prompt", "STDOUT hi"])  # record one entry
    capsys.readouterr()

    monkeypatch.delenv("GMLCACHE_TOKEN", raising=False)
    rc = main(_RUN + ["--prompt", "STDOUT hi"])  # hit -> hydrate -> needs the token
    assert rc == 4
    assert "token" in capsys.readouterr().err.lower()


def test_decrypt_returns_store_to_public(capsys):
    token = _enable(capsys)
    assert main(["decrypt", "--token", token]) == 0
    capsys.readouterr()
    main(["status"])
    assert "encryption  : public" in capsys.readouterr().out


def test_decrypt_with_wrong_token_fails(capsys):
    _enable(capsys)
    assert main(["decrypt", "--token", "definitely-not-the-right-token-xyz"]) == 4
    assert "gmlc:" in capsys.readouterr().err


def test_rotate_swaps_the_token(capsys, monkeypatch):
    run = _RUN + ["--prompt", "STDOUT zz"]
    old = _enable(capsys)
    monkeypatch.setenv("GMLCACHE_TOKEN", old)
    main(run)
    capsys.readouterr()

    assert main(["rotate", "--token", old]) == 0
    new = _token_from(capsys.readouterr().out)
    assert new != old

    monkeypatch.setenv("GMLCACHE_TOKEN", new)
    assert main(run + ["--offline"]) == 0  # new token reads
    capsys.readouterr()
    monkeypatch.setenv("GMLCACHE_TOKEN", old)
    assert main(run + ["--offline"]) == 4  # old token rejected


def test_invalidate_requires_yes_then_wipes_to_public(capsys, monkeypatch):
    token = _enable(capsys)
    monkeypatch.setenv("GMLCACHE_TOKEN", token)
    main(_RUN + ["--prompt", "STDOUT x"])
    capsys.readouterr()

    assert main(["invalidate"]) == 4  # refused without --yes
    assert "yes" in capsys.readouterr().err.lower()

    assert main(["invalidate", "--yes"]) == 0
    capsys.readouterr()
    monkeypatch.delenv("GMLCACHE_TOKEN", raising=False)
    main(["status"])
    assert "encryption  : public" in capsys.readouterr().out
