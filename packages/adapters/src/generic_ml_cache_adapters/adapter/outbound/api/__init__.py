# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""API adapters.

Built-in adapters declare themselves via the ``gmlcache.adapters`` entry-point
group and a ``descriptor()`` classmethod; the discovery layer finds and
constructs them.
"""

from __future__ import annotations
