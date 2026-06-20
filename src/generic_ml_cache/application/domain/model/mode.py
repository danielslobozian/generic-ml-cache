"""Mode."""

from __future__ import annotations

import enum


class Mode(enum.Enum):
    OFFLINE = "offline"
    CACHE = "cache"
    REFRESH = "refresh"
