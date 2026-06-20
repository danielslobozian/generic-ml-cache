"""ProbeStatus."""

from __future__ import annotations

import enum


class ProbeStatus(enum.Enum):
    """The verdict of a read-only cache probe (see :func:`probe`)."""

    HIT = "hit"  # a cassette exists for this exact call
    MISS = "miss"  # cacheable, but no cassette recorded yet
    NON_CACHEABLE = "non-cacheable"  # declares allow-path folders -> never cached
