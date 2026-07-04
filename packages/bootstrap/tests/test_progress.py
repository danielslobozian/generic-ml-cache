# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The driver-facing progress-stream hook (W28).

The CLI's async-jobs runner reaches the NDJSON progress writer through this hook
instead of importing ``generic_ml_cache_adapters.stream`` directly — the exact
``cli -> adapters`` edge W28 removes.
"""

import json
from pathlib import Path

from generic_ml_cache_bootstrap.progress import open_progress_stream


def test_open_progress_stream_writes_ndjson_events(tmp_path: Path):
    events = tmp_path / "events.ndjson"
    writer = open_progress_stream(events)
    try:
        writer.event("started", job="abc")
        writer.event("finished", job="abc")
    finally:
        writer.close()

    lines = events.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["started", "finished"]


def test_open_progress_stream_is_best_effort_on_unwritable_path(tmp_path: Path):
    # A path whose parent is a file (not a directory) cannot be opened; the writer
    # must silently disable itself rather than raise into the caller's hot path.
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    writer = open_progress_stream(blocker / "events.ndjson")
    try:
        writer.event("started")  # must not raise
    finally:
        writer.close()
