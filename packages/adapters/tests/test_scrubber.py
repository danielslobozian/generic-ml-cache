# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Security-grade tests for the diagnostics secret scrubber (CG8).

The scrubber runs on *every* command's log path, so a bug leaks tokens into
``<store>/gmlcache.log`` on every run. Two failure modes matter equally:

  * **under-redaction** — a real secret survives into the log (a leak), and
  * **over-redaction** — an ordinary value (a content-addressed key, a path, a
    UUID) is destroyed, silently corrupting the log — the *dominant* failure mode.

Both are covered below: positive per-format, our own token, negatives / false
positives, the entropy boundary, key-name context, nesting, and idempotency.
"""

from __future__ import annotations

import pytest

from generic_ml_cache_adapters.adapter.out.diagnostics.structlog_diagnostics_adapter import (
    _scrub_processor,
    _scrub_string,
    _scrub_value,
)

# A real 64-hex string: shape-identical to our legacy bare GMLCACHE_TOKEN *and* to a
# SHA-256 content-addressed cache key. It must be preserved by value (else every log
# line naming a cache key is destroyed) and redacted only by key name / gmlc_ prefix.
_BARE_HEX_64 = "a3f5c9e1b7d2486092f456ab7788ccddeeff00112233445566778899aabbccdd"


# --- positive per-format: each MUST be redacted ------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer ya29.a0ARrdaM8xYzABC123defGHI456jkl",  # OAuth bearer
        "api_key apikey_ABC123def456GHI789jkl012MNO345pqr678",  # header form
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJ",  # JWT
        "token ghp_16C7e42F292c6912E7710c838347Ae178B4a12cd",  # GitHub PAT
        "AKIAIOSFODNN7EXAMPLE",  # AWS access key id
        "AIzaSyD-1234567890abcDEFghIJKlmNOPqrstuvwx",  # Google API key
        "c2VjcmV0LXZhbHVlLXRoYXQtaXMtdmVyeS1sb25nQUJD",  # base64 >= 32
        "MixedCaseSecret0123456789ABCDEFabcdef0123",  # hex/alnum >= 32, mixed case
    ],
)
def test_positive_formats_are_redacted(raw: str) -> None:
    scrubbed = _scrub_string(raw)
    assert scrubbed != raw
    assert any(marker in scrubbed for marker in ("[token]", "[secret]", "[email]"))


def test_email_is_redacted() -> None:
    assert _scrub_string("contact alice@example.com now") == "contact [email] now"


# --- our own encryption token ------------------------------------------------


def test_gmlc_prefixed_token_is_value_redacted() -> None:
    # CG9-bis provenance prefix makes the token value-redactable in free text.
    raw = f"store token is gmlc_{_BARE_HEX_64} for this run"
    assert f"gmlc_{_BARE_HEX_64}" not in _scrub_string(raw)
    assert "[secret]" in _scrub_string(raw)


def test_legacy_bare_token_is_redacted_by_key_name() -> None:
    # A bare 64-hex token is shape-identical to a content key, so it is NOT value-
    # redactable; the key-name rule is what protects it when logged as a field.
    for key in ("token", "access_token", "secret"):
        result = _scrub_processor(None, "info", {key: _BARE_HEX_64})
        assert result[key] == "[redacted]"


# --- negative / false-positive: each MUST be preserved -----------------------


@pytest.mark.parametrize(
    "raw",
    [
        "/run/secrets/db_username",  # a file path, not a secret
        "550e8400-e29b-41d4-a716-446655440000",  # a UUID
        _BARE_HEX_64,  # a SHA-256 content key (bare lowercase hex)
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",  # dependency hash
        "the quick brown fox jumps over the lazy dog",  # ordinary prose
        "1.2.3-rc4",  # a version string
        "AKIALOOKALIKELOWERcasexyz",  # AKIA-lookalike, not 16 upper-hex
    ],
)
def test_negatives_are_preserved(raw: str) -> None:
    assert _scrub_string(raw) == raw


# --- entropy boundary --------------------------------------------------------


def test_entropy_boundary() -> None:
    # The rule needs one [A-Z+/] anchor followed by >= 30 more chars, i.e. >= 31 total.
    below = "A" + "b" * 29  # 30 chars: 1 + 29 < threshold -> preserved
    at_threshold = "A" + "b" * 30  # 31 chars: 1 + 30 -> redacted
    assert _scrub_string(below) == below
    assert _scrub_string(at_threshold) == "[secret]"


# --- key-name context weighting ----------------------------------------------


def test_same_value_redacted_under_sensitive_key_only() -> None:
    high_entropy = "MixedCaseSecret0123456789ABCDEFabcdef0123"
    plain_hex_id = _BARE_HEX_64  # looks like a DB id / content key
    # Under a sensitive key: redacted by name regardless of shape.
    assert _scrub_processor(None, "info", {"api_key": plain_hex_id})["api_key"] == "[redacted]"
    # Under an ordinary key: the value rule still catches the high-entropy secret,
    # but leaves the bare-hex id (a legitimate identifier) intact.
    result = _scrub_processor(None, "info", {"execution_key": plain_hex_id, "note": high_entropy})
    assert result["execution_key"] == plain_hex_id
    assert result["note"] == "[secret]"


# --- nested structures -------------------------------------------------------


def test_secret_nested_in_mapping_is_redacted() -> None:
    scrubbed = _scrub_value({"outer": {"token": _BARE_HEX_64, "ok": "value"}})
    assert scrubbed["outer"]["token"] == "[redacted]"
    assert scrubbed["outer"]["ok"] == "value"


def test_secret_nested_in_sequence_is_redacted() -> None:
    scrubbed = _scrub_value(["ok", f"gmlc_{_BARE_HEX_64}"])
    assert scrubbed[0] == "ok"
    assert scrubbed[1] == "[secret]"


# --- idempotency & non-string passthrough ------------------------------------


def test_scrubbing_is_idempotent() -> None:
    once = _scrub_string(f"Bearer gmlc_{_BARE_HEX_64}")
    assert _scrub_string(once) == once


def test_non_string_scalars_pass_through() -> None:
    assert _scrub_value(42) == 42
    assert _scrub_value(None) is None
    assert _scrub_value(True) is True
