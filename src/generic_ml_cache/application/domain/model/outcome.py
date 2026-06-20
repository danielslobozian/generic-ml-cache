"""Outcome."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache.cassette import Cassette, Response


@dataclass
class Outcome:
    """What the cache did and the response it resolved to."""

    response: Response
    hit: bool  # True if served from an existing cassette
    recorded: bool  # True if a real call was made and stored
    cassette: Cassette
    passthrough: bool = False  # True if it ran fresh and stored nothing (allow-path)
    failed_unstored: bool = False  # True if a real call ran, failed (non-zero exit),
