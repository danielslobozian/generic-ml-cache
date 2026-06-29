# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The grant vocabulary: capability names the cache can OPEN for a run.

A grant ENABLES a capability for a single isolated run (network egress, reads
beyond the run folder, a shell, web search); it never restricts. This tuple is
the single source of truth shared by the CLI (the ``--grant`` choices) and every
local client adapter (which opens the matching door via its own config file).
See ``docs/reference/grants.md``.
"""

from __future__ import annotations

from typing import Tuple

#: capabilities the cache can OPEN via each client's uniform config-file mechanism
GRANTS: Tuple[str, ...] = ("net", "read", "write", "shell", "web-search")
