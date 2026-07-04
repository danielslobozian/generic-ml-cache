# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared output-parsing helpers for local CLI client adapters.

Pure text helpers used by the concrete adapters (claude, codex, cursor) to lift
the answer and usage out of a client's structured stdout. They live in the
adapter layer because reading a specific client's output shape is adapter
behavior, not a core port contract.
"""

from __future__ import annotations

import json
from typing import Any, TypeGuard


def is_json_object(candidate: object) -> TypeGuard[dict[str, Any]]:
    """Answer whether a decoded JSON value is an object. The narrowing to
    ``dict[str, Any]`` is sound for values produced by ``json.loads``, which
    only ever builds string-keyed dicts."""
    return isinstance(candidate, dict)


def final_result_object(stdout: str) -> dict[str, Any] | None:
    """Return the client's final result object, whether its output arrived as a
    single JSON object (``--output-format json``) or as the last ``type:result``
    line of an NDJSON stream (``--output-format stream-json``).

    Claude and Cursor emit *the same* result object in both forms, so the recorded
    answer and usage are identical either way -- this is what lets the live stream
    switch the client to streaming mode without changing the stored record. Returns
    ``None`` if nothing parseable is present (the adapter then degrades to raw
    stdout with no usage).
    """
    text = stdout.strip()
    if not text:
        return None
    # Single object (today's --output-format json): parses whole, in one shot.
    try:
        whole_document: object = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        whole_document = None  # not a single object -> NDJSON stream; scan for the result
    if is_json_object(whole_document):
        return whole_document
    last_result_object: dict[str, Any] | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if is_json_object(event) and event.get("type") == "result":
            last_result_object = event
    return last_result_object


def ensure_trailing_newline(text: str) -> str:
    """Append a newline to a client's answer when it lacks one.

    A client's structured (JSON) ``result`` carries the bare answer text, without
    the trailing newline a real CLI prints when it shows that answer. Without this
    the replayed answer butts against the next shell prompt, and a piped capture
    (``gmlcache run ... > file``) lacks the conventional final newline. Normalizing
    here -- at the adapter boundary -- keeps record and replay byte-identical (the
    recorded form simply includes the newline). Empty text is left untouched."""
    if text and not text.endswith("\n"):
        return text + "\n"
    return text
