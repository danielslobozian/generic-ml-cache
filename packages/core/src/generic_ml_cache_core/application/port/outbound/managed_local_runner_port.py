# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedLocalRunnerPort — the managed-execution role of a local CLI client (W24).

One of the four role ports the fat ``LocalClientPort`` was split into (V32/B-1 ISP):
a managed run needs only to resolve the executable, stage its inputs, and make the
call — not to list models or print a version. ``resolve_executable`` overlaps the
passthrough runner and the probe (a legitimate role overlap, like ``total_stored_
bytes`` across Inspect+Purge): each needs it for its own job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.workspace import Workspace


class ManagedLocalRunnerPort(ABC):
    """Run one isolated managed local execution against a workspace the use case
    already prepared."""

    @abstractmethod
    def resolve_executable(self, override: str | None) -> str:
        """Resolve the client's executable (an explicit path or a PATH lookup)."""

    @abstractmethod
    def stage_inputs(self, request: ManagedLocalRequest, workspace: Workspace) -> None:
        """Write any input files the client reads into the workspace's run folder,
        *before* the managed use case snapshots it (so inputs are baseline, not
        mistaken for output). Default for most clients is a no-op."""

    @abstractmethod
    def execute_managed(self, request: ManagedLocalRequest, workspace: Workspace) -> ClientAnswer:
        """Make the managed call against a workspace the use case already prepared:
        build the argv, launch the client, map its output to an answer. The adapter
        does NOT create, snapshot, or diff the workspace — that is the use case's job."""
