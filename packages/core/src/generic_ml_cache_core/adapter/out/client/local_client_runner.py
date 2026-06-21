# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalClientRunner: the ClientRunnerPort over the isolated client machinery."""

from __future__ import annotations

from typing import Callable, Optional

from generic_ml_cache_core.adapter.out.client.isolation import record_real_call
from generic_ml_cache_core.adapter.out.client.registry import get_adapter
from generic_ml_cache_core.application.domain.model.run.client_run_request import ClientRunRequest
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort


class LocalClientRunner(ClientRunnerPort):
    """Runs a managed local client in isolation and returns its raw result.

    Wraps the isolation machinery (``record_real_call``): it resolves the client
    adapter and executable, opens the read-door for the declared input files and
    allow-path folders, launches the client, and returns the captured
    ``ClientRunResult``. The executable override (per client) and the timeout are
    injected from the composition root's config.
    """

    def __init__(
        self,
        executable_override: Optional[Callable[[str], Optional[str]]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._executable_override = executable_override or (lambda _client: None)
        self._timeout = timeout

    def run(self, client_run_request: ClientRunRequest) -> ClientRunResult:
        adapter = get_adapter(client_run_request.client)
        executable = adapter.resolve_executable(
            self._executable_override(client_run_request.client)
        )
        return record_real_call(
            adapter=adapter,
            executable=executable,
            model=client_run_request.model,
            effort=client_run_request.effort,
            context=client_run_request.context,
            prompt=client_run_request.prompt,
            user_system_prompt=client_run_request.user_system_prompt,
            timeout=self._timeout,
            allowed_read_paths=sorted(
                [*client_run_request.input_file_paths, *client_run_request.allow_paths]
            ),
            add_dir_paths=sorted(client_run_request.allow_paths),
            client_args=list(client_run_request.client_args),
            grants=list(client_run_request.grants),
        )
