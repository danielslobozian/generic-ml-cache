# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Alias mode (`gmlcache alias <client> -- <native args>`).

The thin native-client wrapper: everything after the client is an opaque tail,
forwarded verbatim and keyed (by fingerprint) as the cache identity. No isolation,
no file capture -- a replay reproduces the native call's stdout/stderr/exit.

The ``fake`` adapter's executable is the Python interpreter, so a native tail of
``-c <snippet>`` runs that snippet -- a portable stand-in for a real native call.
"""

from __future__ import annotations

from generic_ml_cache_cli.cli import main

# `fake`'s executable is sys.executable (python), so these tails run python directly.
_HELLO = ["-c", "import sys; sys.stdout.write('hello\\n')"]
_BYE = ["-c", "import sys; sys.stdout.write('bye\\n')"]
_FAIL = ["-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(7)"]


def test_alias_runs_the_native_call_and_relays_output(capsys):
    assert main(["alias", "fake", *_HELLO]) == 0
    assert capsys.readouterr().out == "hello\n"


def test_alias_replays_an_identical_tail_from_cache(capsys):
    # First call records; a non-deterministic source proves the second is a replay.
    tail = ["-c", "import os; print(os.getpid())"]
    assert main(["alias", "fake", *tail]) == 0
    first = capsys.readouterr().out
    assert main(["alias", "fake", *tail]) == 0
    second = capsys.readouterr().out
    assert first == second  # a fresh run would print a different pid


def test_alias_keys_on_the_raw_tail(capsys):
    assert main(["alias", "fake", *_HELLO]) == 0
    assert capsys.readouterr().out == "hello\n"
    # A different tail is a different identity -> its own call, its own output.
    assert main(["alias", "fake", *_BYE]) == 0
    assert capsys.readouterr().out == "bye\n"


def test_alias_offline_miss_is_exit_3(capsys):
    rc = main(["alias", "--offline", "fake", "-c", "print('never recorded')"])
    assert rc == 3
    assert "offline miss" in capsys.readouterr().err


def test_alias_force_refreshes_a_recorded_call(capsys):
    tail = ["-c", "import os; print(os.getpid())"]
    assert main(["alias", "fake", *tail]) == 0
    recorded = capsys.readouterr().out
    assert main(["alias", "--force", "fake", *tail]) == 0
    refreshed = capsys.readouterr().out
    assert recorded != refreshed  # --force re-ran the native call


def test_alias_relays_a_native_failure_verbatim(capsys):
    # The native exit code and stderr surface exactly; nothing is rewritten.
    assert main(["alias", "fake", *_FAIL]) == 7
    assert capsys.readouterr().err == "boom\n"


def test_alias_never_serves_a_recorded_failure_as_a_hit(capsys):
    # --record-on-error keeps the failed call as history, but the cache never serves
    # a failure as a hit -- a later offline call still misses (exit 3).
    assert main(["alias", "--record-on-error", "fake", *_FAIL]) == 7
    capsys.readouterr()
    assert main(["alias", "--offline", "fake", *_FAIL]) == 3
    assert "offline miss" in capsys.readouterr().err


def test_alias_accepts_an_explicit_double_dash_separator(capsys):
    # `alias fake -- <tail>` strips the separator; identity matches the bare form.
    assert main(["alias", "fake", "--", *_HELLO]) == 0
    assert capsys.readouterr().out == "hello\n"
    # Same call without the separator hits the cache (offline proves it).
    assert main(["alias", "--offline", "fake", *_HELLO]) == 0
    assert capsys.readouterr().out == "hello\n"


def test_alias_does_not_interpret_native_flags_as_its_own(capsys):
    # `--offline` AFTER the client is native (here, ignored by python -c), not a
    # gmlcache flag: the call runs and records rather than failing as an offline miss.
    assert main(["alias", "fake", "-c", "print('ok')", "--offline"]) == 0
    assert capsys.readouterr().out == "ok\n"
