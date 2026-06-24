# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AbstractPassthroughLocalAdapter — passthrough runner for a specific client."""

from __future__ import annotations

import subprocess
from typing import Optional

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort

_TEXT_ENCODING = "utf-8"


class AbstractPassthroughLocalAdapter(MlRunnerPort):
    """Passthrough runner tied to one registered client adapter.

    Implements MlRunnerPort: reads native_args from the MlRequest and forwards
    them verbatim to the client binary. No isolation, no file capture, no
    adapter-specific argv building. The client runs where the caller invoked it.
    """

    def __init__(
        self,
        adapter: ClientAdapter,
        executable_override: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._adapter = adapter
        self._executable_override = executable_override
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"pass-{self._adapter.name}"

    @property
    def execution_kind(self) -> ExecutionKind:
        return ExecutionKind.LOCAL_PASSTHROUGH

    def run(self, request: MlRequest) -> ClientRunResult:
        """Launch the client with native_args from request and return the result."""
        executable = self._adapter.resolve_executable(self._executable_override)
        completed = subprocess.run(
            [executable, *request.native_args],
            capture_output=True,
            timeout=self._timeout,
            check=False,
        )
        return ClientRunResult(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode(_TEXT_ENCODING, errors="replace"),
            stderr=completed.stderr.decode(_TEXT_ENCODING, errors="replace"),
        )
