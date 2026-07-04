# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests for StructlogDiagnosticsAdapter — the real log-write path.

These complement the scrubber unit tests (test_scrubber.py) by proving the
scrubber actually runs on the live path: a secret handed to a real ``.info`` /
``.error`` call is redacted in the bytes written to ``<store>/gmlcache.log``.
They also exercise the renderer, level filtering, exception rendering, and the
never-propagate guarantee.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from generic_ml_cache_adapters.adapter.outbound.diagnostics.structlog_diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
)

_SECRET = "a3f5c9e1b7d2486092f456ab7788ccddeeff00112233445566778899aabbccdd"

MakeDiag = Callable[..., "tuple[StructlogDiagnosticsAdapter, Path]"]


@pytest.fixture
def make_diag(tmp_path: Path) -> object:
    """Factory for adapters that are closed at teardown, so the open log-file
    handle never trips the ResourceWarning-as-error gate (CG9)."""
    created: list[StructlogDiagnosticsAdapter] = []

    def _factory(
        level: str = "DEBUG", fmt: str = "text"
    ) -> tuple[StructlogDiagnosticsAdapter, Path]:
        log_file = tmp_path / "gmlcache.log"
        diag = StructlogDiagnosticsAdapter(log_file, level=level, fmt=fmt)
        created.append(diag)
        return diag, log_file

    yield _factory
    for diag in created:
        diag.close()


def test_info_writes_a_line(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag()
    diag.info("cache hit", execution_key="abc")
    contents = log_file.read_text(encoding="utf-8")
    assert "cache hit" in contents
    assert "execution_key=abc" in contents


def test_secret_under_sensitive_key_is_redacted_end_to_end(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag()
    diag.info("resolving", token=_SECRET)
    contents = log_file.read_text(encoding="utf-8")
    assert _SECRET not in contents  # the token never reaches the file
    assert "[redacted]" in contents


def test_prefixed_token_in_message_is_redacted_end_to_end(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag()
    diag.info(f"opening store with gmlc_{_SECRET}")
    contents = log_file.read_text(encoding="utf-8")
    assert f"gmlc_{_SECRET}" not in contents
    assert "[secret]" in contents


def test_content_key_survives_end_to_end(make_diag: MakeDiag) -> None:
    # Over-redaction check on the live path: a bare-hex content key must be logged intact.
    diag, log_file = make_diag()
    diag.info("stored", execution_key=_SECRET)
    assert _SECRET in log_file.read_text(encoding="utf-8")


def test_level_below_threshold_is_dropped(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag(level="WARN")
    diag.info("noise")
    diag.warn("kept")
    contents = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "noise" not in contents
    assert "kept" in contents


def test_error_renders_scrubbed_traceback(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag()
    try:
        raise ValueError(f"boom with token gmlc_{_SECRET}")
    except ValueError as exc:
        diag.error("run failed", exc=exc)
    contents = log_file.read_text(encoding="utf-8")
    assert "run failed" in contents
    assert "ValueError" in contents  # the traceback was rendered
    assert f"gmlc_{_SECRET}" not in contents  # ...and scrubbed


def test_caller_and_thread_info_present(make_diag: MakeDiag) -> None:
    diag, log_file = make_diag()
    diag.info("hello")
    contents = log_file.read_text(encoding="utf-8")
    assert ":" in contents  # thread name:id and caller func:lineno both use ':'


def test_json_format_emits_json_lines(make_diag: MakeDiag) -> None:
    import json

    diag, log_file = make_diag(fmt="json")
    diag.info("event happened", api_key=_SECRET)
    line = log_file.read_text(encoding="utf-8").strip().splitlines()[0]
    parsed = json.loads(line)
    assert parsed["event"] == "event happened"
    assert parsed["api_key"] == "[redacted]"


def test_emit_never_propagates_on_unwritable_file(tmp_path: Path) -> None:
    # R5: a diagnostics failure must never break the caller. Point the log at a path
    # whose parent is a file, so opening it raises — the call must still return.
    not_a_dir = tmp_path / "afile"
    not_a_dir.write_text("x", encoding="utf-8")
    diag = StructlogDiagnosticsAdapter(not_a_dir / "nested.log", level="INFO")
    diag.info("this must not raise")  # no exception escapes
    diag.close()
