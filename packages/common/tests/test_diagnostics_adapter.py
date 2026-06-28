"""Tests for StructlogDiagnosticsAdapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from generic_ml_cache_common.diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
    _scrub_string,
)
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort


def _adapter(
    tmp_path: Path, level: str = "DEBUG", fmt: str = "text"
) -> StructlogDiagnosticsAdapter:
    return StructlogDiagnosticsAdapter(tmp_path / "gmlcache.log", level=level, fmt=fmt)


def _lines(tmp_path: Path) -> list:
    return (tmp_path / "gmlcache.log").read_text().splitlines()


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_diagnostics_port(tmp_path: Path) -> None:
    assert isinstance(_adapter(tmp_path), DiagnosticsPort)


# ---------------------------------------------------------------------------
# Never-raise contract (R5)
# ---------------------------------------------------------------------------


def test_debug_does_not_raise(tmp_path: Path) -> None:
    _adapter(tmp_path).debug("msg", key="val")


def test_info_does_not_raise(tmp_path: Path) -> None:
    _adapter(tmp_path).info("msg")


def test_warn_does_not_raise(tmp_path: Path) -> None:
    _adapter(tmp_path).warn("msg")


def test_error_does_not_raise(tmp_path: Path) -> None:
    _adapter(tmp_path).error("msg", exc=ValueError("boom"))


# ---------------------------------------------------------------------------
# Text format — field presence
# ---------------------------------------------------------------------------


def test_text_line_contains_timestamp(tmp_path: Path) -> None:
    _adapter(tmp_path).info("hello")
    assert "2026-" in _lines(tmp_path)[0]


def test_text_line_contains_level(tmp_path: Path) -> None:
    _adapter(tmp_path).info("hello")
    assert "INFO" in _lines(tmp_path)[0]


def test_text_line_contains_thread(tmp_path: Path) -> None:
    _adapter(tmp_path).info("hello")
    assert "MainThread" in _lines(tmp_path)[0]


def test_text_line_contains_message(tmp_path: Path) -> None:
    _adapter(tmp_path).info("cache hit")
    assert "cache hit" in _lines(tmp_path)[0]


def test_text_line_contains_caller(tmp_path: Path) -> None:
    _adapter(tmp_path).info("hello")
    line = _lines(tmp_path)[0]
    assert "test_diagnostics_adapter" in line or ":" in line


def test_text_line_contains_context_key(tmp_path: Path) -> None:
    _adapter(tmp_path).info("msg", execution_key="abc123")
    assert "execution_key=abc123" in _lines(tmp_path)[0]


def test_error_line_contains_traceback(tmp_path: Path) -> None:
    _adapter(tmp_path).error("failed", exc=ValueError("oops"))
    content = (tmp_path / "gmlcache.log").read_text()
    assert "ValueError" in content
    assert "oops" in content


# ---------------------------------------------------------------------------
# Level filtering
# ---------------------------------------------------------------------------


def test_debug_filtered_at_info_level(tmp_path: Path) -> None:
    _adapter(tmp_path, level="INFO").debug("should be dropped")
    assert not (tmp_path / "gmlcache.log").exists()


def test_warn_passes_at_info_level(tmp_path: Path) -> None:
    _adapter(tmp_path, level="INFO").warn("should appear")
    assert _lines(tmp_path)


def test_error_passes_at_warn_level(tmp_path: Path) -> None:
    _adapter(tmp_path, level="WARN").error("should appear")
    assert _lines(tmp_path)


def test_info_filtered_at_error_level(tmp_path: Path) -> None:
    _adapter(tmp_path, level="ERROR").info("should be dropped")
    assert not (tmp_path / "gmlcache.log").exists()


# ---------------------------------------------------------------------------
# PII scrubbing — _scrub_string unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        # E-mail addresses
        ("user@example.com", "[email]"),
        ("error for john.doe@company.org in request", "error for [email] in request"),
        # Bearer / Authorization header values
        ("Bearer sk-abc123defgh456ijklmno", "Bearer [token]"),
        ("token abcdefghijklmnopqrstuvwx", "token [token]"),
        # Long opaque secrets (≥ 32 chars, mixed-case / base64 — real token shape).
        # The non-secret prefix (sk-ant-api03-) is left intact; the secret portion is scrubbed.
        ("sk-ant-api03-" + "AbCdEfGh" * 5, "sk-ant-api03-[secret]"),
        # Pure lowercase hex (SHA-256 content key) must NOT be scrubbed
        ("a" * 64, "a" * 64),
        # Short values are left alone
        ("abc123", "abc123"),
        ("hello world", "hello world"),
        # Multiple occurrences in one string
        (
            "contact user@a.com or user@b.com",
            "contact [email] or [email]",
        ),
    ],
)
def test_scrub_string(raw: str, expected: str) -> None:
    assert _scrub_string(raw) == expected


# ---------------------------------------------------------------------------
# PII scrubbing — integration through the adapter
# ---------------------------------------------------------------------------


def test_sensitive_key_is_redacted(tmp_path: Path) -> None:
    _adapter(tmp_path).info("msg", token="super-secret-value")
    assert "super-secret-value" not in (tmp_path / "gmlcache.log").read_text()
    assert "[redacted]" in (tmp_path / "gmlcache.log").read_text()


def test_email_in_value_is_redacted(tmp_path: Path) -> None:
    _adapter(tmp_path).info("msg", detail="sent to alice@example.com")
    log = (tmp_path / "gmlcache.log").read_text()
    assert "alice@example.com" not in log
    assert "[email]" in log


def test_email_in_traceback_is_redacted(tmp_path: Path) -> None:
    exc = ValueError("request failed for user@secret.com")
    _adapter(tmp_path).error("err", exc=exc)
    log = (tmp_path / "gmlcache.log").read_text()
    assert "user@secret.com" not in log
    assert "[email]" in log


def test_non_sensitive_key_is_not_redacted(tmp_path: Path) -> None:
    _adapter(tmp_path).info("msg", execution_key="abc123", session="uuid-xyz")
    log = (tmp_path / "gmlcache.log").read_text()
    assert "abc123" in log
    assert "uuid-xyz" in log


def test_password_key_is_redacted(tmp_path: Path) -> None:
    _adapter(tmp_path).warn("auth failed", password="hunter2")
    log = (tmp_path / "gmlcache.log").read_text()
    assert "hunter2" not in log
    assert "[redacted]" in log


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------


def test_json_format_is_valid_json(tmp_path: Path) -> None:
    import json

    _adapter(tmp_path, fmt="json").info("msg", key="val")
    data = json.loads(_lines(tmp_path)[0])
    assert data["event"] == "msg"
    assert data["key"] == "val"
