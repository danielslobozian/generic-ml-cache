# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalClientProbePort — the availability-probe role of a local CLI client (W24).

One of the four role ports the fat ``LocalClientPort`` was split into: the ``doctor``
availability check needs only to resolve the executable and ask its version — not to
run a managed/passthrough call or list models. ``resolve_executable`` overlaps the
two runner ports (a legitimate role overlap).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LocalClientProbePort(ABC):
    """Probe a local CLI client's availability (used by ``doctor``)."""

    @abstractmethod
    def resolve_executable(self, override: str | None) -> str:
        """Resolve the client's executable (an explicit path or a PATH lookup)."""

    @abstractmethod
    def version_argv(self, executable: str) -> list[str]:
        """Argv that prints the client's version string. Used by ``doctor``."""
