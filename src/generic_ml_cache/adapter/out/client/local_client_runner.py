# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalClientRunner: the ClientRunnerPort over the isolated client machinery."""

from __future__ import annotations

from typing import Callable, List, Optional

from generic_ml_cache.adapter.out.client.isolation import record_real_call
from generic_ml_cache.adapter.out.client.registry import get_adapter
from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.client_run_result import (
    ClientRunResult,
    GeneratedFile,
)
from generic_ml_cache.application.domain.model.token_usage import TokenUsage
from generic_ml_cache.application.port.out.client_runner_port import ClientRunnerPort


class LocalClientRunner(ClientRunnerPort):
    """Runs a managed local client in isolation and returns its raw result.

    Wraps the existing isolation machinery (``record_real_call``): it resolves the
    client adapter and executable, opens the read-door for the declared input
    files and allow-path folders, launches the client, and translates the captured
    response into a ``ClientRunResult``. The executable override (per client) and
    the timeout are injected from the composition root's config.
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
        run_result = record_real_call(
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
        return _to_client_run_result(run_result.response)


def _to_client_run_result(response) -> ClientRunResult:
    """Translate the isolation layer's response (old domain types) into the new
    ClientRunResult at the adapter boundary."""
    files: List[GeneratedFile] = [
        GeneratedFile(name=captured_file.path, content=captured_file.to_bytes())
        for captured_file in response.files
    ]
    token_usage = (
        TokenUsage.from_dict(response.usage.to_dict()) if response.usage is not None else None
    )
    return ClientRunResult(
        exit_code=response.exit,
        stdout=response.stdout,
        stderr=response.stderr,
        files=files,
        token_usage=token_usage,
    )
