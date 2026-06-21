# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PassthroughClientRunner: the PassthroughRunnerPort over a direct launch."""

from __future__ import annotations

import subprocess
from typing import Callable, List, Optional

from generic_ml_cache.adapter.out.client.registry import get_adapter
from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.port.out.passthrough_runner_port import PassthroughRunnerPort

_TEXT_ENCODING = "utf-8"


class PassthroughClientRunner(PassthroughRunnerPort):
    """Runs a client with its opaque native args, in the caller's own folder.

    No isolation, no file capture: it resolves the client executable, forwards the
    native arguments verbatim, and captures stdout/stderr/exit. Output bytes are
    decoded leniently so unusual client output never crashes the run. The
    executable override and timeout are injected from the composition root.
    """

    def __init__(
        self,
        executable_override: Optional[Callable[[str], Optional[str]]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._executable_override = executable_override or (lambda _client: None)
        self._timeout = timeout

    def run(self, client: str, native_args: List[str]) -> ClientRunResult:
        adapter = get_adapter(client)
        executable = adapter.resolve_executable(self._executable_override(client))
        completed = subprocess.run(
            [executable, *native_args],
            capture_output=True,
            timeout=self._timeout,
            check=False,
        )
        return ClientRunResult(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode(_TEXT_ENCODING, errors="replace"),
            stderr=completed.stderr.decode(_TEXT_ENCODING, errors="replace"),
        )
