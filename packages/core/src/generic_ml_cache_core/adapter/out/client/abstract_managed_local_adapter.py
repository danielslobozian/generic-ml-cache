# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AbstractManagedLocalAdapter — template base for managed local ML clients."""

from __future__ import annotations

from typing import Optional

from generic_ml_cache_core.adapter.out.client.isolation import record_real_call
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort


class AbstractManagedLocalAdapter(ClientAdapter, ClientRunnerPort):
    """Template base for managed local ML client adapters.

    Absorbs the orchestration previously split across LocalClientRunner and
    registry dispatch: each concrete subclass IS the specific adapter. The
    port's run(MlRequest) is fully implemented here; subclasses supply the
    adapter-specific methods (build_argv, parse_output, etc.).

    Execution config (executable override, subprocess timeout, live-progress
    stream path) is injected at construction time by the composition root,
    not discovered at call time.
    """

    def __init__(
        self,
        executable_override: Optional[str] = None,
        timeout: Optional[float] = None,
        stream_path: Optional[str] = None,
    ) -> None:
        self._executable_override = executable_override
        self._timeout = timeout
        self._stream_path = stream_path

    def run(self, request: MlRequest) -> ClientRunResult:
        """Launch this client in isolation and return the raw result."""
        executable = self.resolve_executable(self._executable_override)
        return record_real_call(
            adapter=self,
            executable=executable,
            model=request.model,
            effort=request.effort,
            context=request.context,
            prompt=request.prompt,
            user_system_prompt=request.user_system_prompt,
            timeout=self._timeout,
            allowed_read_paths=sorted([*request.input_file_paths, *request.allow_paths]),
            add_dir_paths=sorted(request.allow_paths),
            client_args=list(request.client_args),
            grants=list(request.grants),
            stream_path=self._stream_path,
        )
