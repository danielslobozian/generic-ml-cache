# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for StreamWriter — the best-effort live-progress NDJSON emitter."""

from __future__ import annotations

import json

from generic_ml_cache_adapters.stream import StreamWriter


def test_stream_writer_writes_event_to_file(tmp_path):
    stream_path = tmp_path / "progress.ndjson"
    writer = StreamWriter(stream_path)
    writer.event("run.start", client="claude", model="sonnet")
    writer.close()
    lines = stream_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["kind"] == "run.start"
    assert record["client"] == "claude"
    assert record["model"] == "sonnet"


def test_stream_writer_omits_none_fields(tmp_path):
    stream_path = tmp_path / "progress.ndjson"
    writer = StreamWriter(stream_path)
    writer.event("run.start", client="claude", effort=None)
    writer.close()
    record = json.loads(stream_path.read_text(encoding="utf-8").strip())
    assert "effort" not in record


def test_stream_writer_silently_disables_when_path_is_unwritable(tmp_path):
    unwritable_path = tmp_path / "no-such-dir" / "deep" / "progress.ndjson"
    unwritable_path.parent.mkdir(parents=True)
    unwritable_path.parent.chmod(0o444)
    try:
        writer = StreamWriter(unwritable_path)
        writer.event("run.start", client="claude")
        writer.close()
    finally:
        unwritable_path.parent.chmod(0o755)


def test_stream_writer_event_is_noop_when_fh_is_none(tmp_path):
    unwritable_path = tmp_path / "no-dir" / "progress.ndjson"
    unwritable_path.parent.mkdir(parents=True)
    unwritable_path.parent.chmod(0o444)
    try:
        writer = StreamWriter(unwritable_path)
        writer.event("should-not-raise")
        writer.close()
    finally:
        unwritable_path.parent.chmod(0o755)


def test_stream_writer_event_swallows_write_error(tmp_path):
    stream_path = tmp_path / "progress.ndjson"
    writer = StreamWriter(stream_path)
    writer.close()
    writer.event("after-close")
