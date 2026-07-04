# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ComposedLocalClient — the LocalClientPort surface, delegated to a CliRuntime.

Every local CLI client adapter subclasses this base and calls ``wire_cli_client``
from its ``__init__`` to set ``self._call``. The base presents the never-overridden
LocalClientPort methods as thin delegations to that composed runtime — no call
logic lives here; it lives once in :class:`CliRuntime`. The base exists so an
adapter *nominally* implements ``LocalClientPort`` (``class X(ComposedLocalClient)``):
a half-built adapter fails to instantiate, which a structural Protocol could not
guarantee. A client that lists models (e.g. cursor) overrides ``models_argv`` and
``parse_model_list`` on its own class; the defaults here mean "no model listing".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.workspace import Workspace
from generic_ml_cache_core.application.port.outbound.local_client_port import LocalClientPort

if TYPE_CHECKING:
    from generic_ml_cache_adapters.adapter.outbound.client.cli_runtime import CliRuntime


class ComposedLocalClient(LocalClientPort):
    """Base for local CLI adapters: the LocalClientPort surface as delegations to
    the composed ``CliRuntime`` (``self._call``), wired in by ``wire_cli_client``."""

    _call: CliRuntime

    def stage_inputs(self, request: ManagedLocalRequest, workspace: Workspace) -> None:
        self._call.stage_inputs(request, workspace)

    def execute_managed(self, request: ManagedLocalRequest, workspace: Workspace) -> ClientAnswer:
        return self._call.execute_managed(request, workspace)

    def execute_passthrough(self, request: PassthroughRequest) -> ClientAnswer:
        return self._call.execute_passthrough(request)

    def resolve_executable(self, override: str | None) -> str:
        return self._call.resolve_executable(override)

    def version_argv(self, executable: str) -> list[str]:
        return self._call.version_argv(executable)

    def models_argv(self, executable: str) -> list[str] | None:
        return self._call.models_argv(executable)

    def parse_model_list(self, stdout: str) -> list[ModelInfo]:
        # No model listing by default; a listing client overrides this (and
        # models_argv). The port contract calls it only when models_argv is non-None,
        # which the default models_argv (delegating to CliRuntime) never is.
        return []
