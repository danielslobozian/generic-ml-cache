# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalClientPort — pure outbound port for local CLI client adapters.

A local client adapter represents ONE external system (e.g. the Claude CLI). It
translates a request into an answer: the managed-execution use case prepares an
isolated workspace, hands it to the adapter to make the call, then captures the
artifacts itself. The adapter performs the call; it owns no workspace lifecycle.

The port carries no subprocess/filesystem/argv knowledge in its contract — those
are the adapter's private implementation (it composes a CliRuntime for them).
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.workspace import Workspace


@runtime_checkable
class LocalClientPort(Protocol):
    """Outbound port for one local CLI client (one adapter = one external system)."""

    def stage_inputs(self, request: ManagedLocalRequest, workspace: Workspace) -> None:
        """Write any input files the client reads into the workspace's run folder,
        *before* the managed use case snapshots it (so inputs are baseline, not
        mistaken for output). Default for most clients is a no-op."""
        ...

    def execute_managed(self, request: ManagedLocalRequest, workspace: Workspace) -> ClientAnswer:
        """Make the managed call against a workspace the use case already prepared:
        build the argv, launch the client, map its output to an answer. The adapter
        does NOT create, snapshot, or diff the workspace — that is the use case's job."""
        ...

    def execute_passthrough(self, request: PassthroughRequest) -> ClientAnswer:
        """Forward native args to the client verbatim and map the result to an
        answer. No workspace, no isolation, no artifact capture — a raw relay."""
        ...

    def resolve_executable(self, override: Optional[str]) -> str:
        """Resolve the client's executable (an explicit path or a PATH lookup)."""
        ...

    def version_argv(self, executable: str) -> List[str]:
        """Argv that prints the client's version string. Used by ``doctor``."""
        ...

    def models_argv(self, executable: str) -> Optional[List[str]]:
        """Argv to enumerate available models, or ``None`` if unsupported."""
        ...

    def parse_model_list(self, stdout: str) -> List[ModelInfo]:
        """Structure the client's raw model-list output into ``ModelInfo`` objects.
        Only called when :meth:`models_argv` is non-``None``."""
        ...
