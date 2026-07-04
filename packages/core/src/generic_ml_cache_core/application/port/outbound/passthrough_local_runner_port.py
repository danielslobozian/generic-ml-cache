# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PassthroughLocalRunnerPort — the passthrough role of a local CLI client (W24).

One of the four role ports the fat ``LocalClientPort`` was split into: a raw relay
needs only to resolve the executable and forward native args — no workspace, no
staging, no artifact capture. ``resolve_executable`` overlaps the managed runner and
the probe (a legitimate role overlap).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)


class PassthroughLocalRunnerPort(ABC):
    """Relay a native passthrough call through a local CLI client, verbatim."""

    @abstractmethod
    def resolve_executable(self, override: str | None) -> str:
        """Resolve the client's executable (an explicit path or a PATH lookup)."""

    @abstractmethod
    def execute_passthrough(self, request: PassthroughRequest) -> ClientAnswer:
        """Forward native args to the client verbatim and map the result to an
        answer. No workspace, no isolation, no artifact capture — a raw relay."""
