# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CacheMode."""

from __future__ import annotations

import enum


class CacheMode(enum.Enum):
    """Cache resolution policy for an MlExecution.

    CACHE   -- serve from cache on a hit; call the client and record on a miss.
               Default.
    OFFLINE -- serve from cache only; a miss raises an error.
    REFRESH -- always call the client and overwrite any existing stored output.
    """

    CACHE = "cache"
    OFFLINE = "offline"
    REFRESH = "refresh"
