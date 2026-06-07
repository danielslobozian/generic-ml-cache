# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from generic_ml_cache import CapturedFile, Cassette, Response
from generic_ml_cache.prime_directive import PRIME_DIRECTIVE


def make_cassette() -> Cassette:
    return Cassette(
        client="fake",
        model="m1",
        effort="high",
        input_data={"context": "ctx\n", "prompt": "do it\n"},
        response=Response(
            stdout="ok\n",
            stderr="warn\n",
            exit=0,
            files=[CapturedFile("out/result.txt", "result\n")],
        ),
    )


def test_json_round_trip():
    c = make_cassette()
    restored = Cassette.from_json(c.to_json())
    assert restored.client == c.client
    assert restored.model == c.model
    assert restored.effort == c.effort
    assert restored.input_data == c.input_data
    assert restored.response.stdout == c.response.stdout
    assert restored.response.exit == c.response.exit
    assert restored.response.files[0].path == "out/result.txt"
    assert restored.match_key == c.match_key


def test_json_is_stable_and_sorted():
    c = make_cassette()
    # serializing twice gives identical bytes (diff-friendly)
    assert c.to_json() == c.to_json()


def test_prime_directive_never_stored_in_cassette():
    c = make_cassette()
    assert PRIME_DIRECTIVE not in c.to_json()
    assert "PRIME DIRECTIVE" not in c.to_json()


def test_command_wording_not_stored():
    """The cassette stores semantic launch params, never the argv/command text."""
    c = make_cassette()
    blob = c.to_json()
    assert "--model" not in blob
    assert "--append-system-prompt" not in blob


def test_binary_content_survives_via_base64():
    raw = b"\xff\xfe\x00\x01binary"
    cf = CapturedFile.from_bytes("blob.bin", raw)
    assert cf.encoding == "base64"
    assert cf.to_bytes() == raw
