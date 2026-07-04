# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ComposedLocalClient — the LocalClientPort surface, delegated to a CliRuntime.

Every local CLI client adapter subclasses this base and calls ``wire_cli_client``
from its ``__init__`` to set ``self.call``. The base presents the never-overridden
LocalClientPort methods as thin delegations to that composed runtime — no call
logic lives here; it lives once in :class:`CliRuntime`. The base exists so an
adapter *nominally* implements ``LocalClientPort`` (``class X(ComposedLocalClient)``):
a half-built adapter fails to instantiate, which a structural Protocol could not
guarantee. A client that lists models (e.g. cursor) overrides ``models_argv`` and
``parse_model_list`` on its own class; the defaults here mean "no model listing".
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

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
    from collections.abc import Sequence
    from pathlib import Path

    from generic_ml_cache_adapters.adapter.outbound.client.cli_runtime import CliRuntime


class ComposedLocalClient(LocalClientPort):
    """Base for local CLI adapters: the LocalClientPort surface as delegations to
    the composed ``CliRuntime`` (``self.call``), wired in by ``wire_cli_client``.
    ``call`` is set from outside the class (by ``wire_cli_client``), so it is a
    public attribute, not a private one."""

    #: The adapter's registry name (e.g. ``"claude"``).
    name: ClassVar[str]
    #: The executable looked up on PATH when no override is given.
    default_executable: ClassVar[str]

    call: CliRuntime

    @abstractmethod
    def build_argv(
        self,
        executable: str,
        run_dir: Path,
        model: str,
        effort: str,
        context: str,
        prompt: str,
        system_prompt: str,
        client_args: Sequence[str] = (),
        grants: Sequence[str] = (),
    ) -> list[str]:
        """Translate the request into the client's own command line. The one hook
        every adapter must supply; the optional hooks (``stdin_payload``,
        ``stream_event``, …) are looked up dynamically by the runtime."""

    def stage_inputs(self, request: ManagedLocalRequest, workspace: Workspace) -> None:
        self.call.stage_inputs(request, workspace)

    def execute_managed(self, request: ManagedLocalRequest, workspace: Workspace) -> ClientAnswer:
        return self.call.execute_managed(request, workspace)

    def execute_passthrough(self, request: PassthroughRequest) -> ClientAnswer:
        return self.call.execute_passthrough(request)

    def resolve_executable(self, override: str | None) -> str:
        return self.call.resolve_executable(override)

    def version_argv(self, executable: str) -> list[str]:
        return self.call.version_argv(executable)

    def models_argv(self, executable: str) -> list[str] | None:
        return self.call.models_argv(executable)

    def parse_model_list(self, stdout: str) -> list[ModelInfo]:
        # No model listing by default; a listing client overrides this (and
        # models_argv). The port contract calls it only when models_argv is non-None,
        # which the default models_argv (delegating to CliRuntime) never is.
        return []
