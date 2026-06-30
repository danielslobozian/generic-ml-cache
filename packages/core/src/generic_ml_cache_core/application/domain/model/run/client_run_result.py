# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientRunResult and GeneratedFile."""

from __future__ import annotations

from dataclasses import dataclass, field

from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage


@dataclass(frozen=True)
class GeneratedFile:
    """One file the client produced, captured raw — name and bytes only.

    No checksum and no blob key: storage is the use case's job, not the runner's.
    """

    name: str
    content: bytes


@dataclass(frozen=True)
class ClientRunResult:
    """The raw, transient result of a client run, assembled by the use case.

    For a managed run the use case combines the adapter's ClientAnswer with the
    files captured from the workspace into this; an API run maps its reply here
    directly. Nothing here is stored yet: the use case turns this into Artifacts
    (hash each piece, put it in the blob store) and assembles the MlExecution.
    The runner itself never hashes, never computes a key, never stores.

    It also interprets its own ``exit_code`` into a run outcome — that rule reads
    only this object's data, so it lives here, not in the use case.
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    files: list[GeneratedFile] = field(default_factory=list)
    #: Token accounting the runner observed (a structured client or an API), or
    #: None when none was reported. Carried to MlExecution.token_usage by the
    #: shared flow; not stored as output bytes (it is database-bound accounting).
    token_usage: TokenUsage | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    def outcome(self) -> ExecutionState:
        return ExecutionState.SUCCESS if self.succeeded else ExecutionState.FAILED

    def failure(self) -> ExecutionFailure | None:
        if self.succeeded:
            return None
        return ExecutionFailure(
            reason=FailureReason.NONZERO_EXIT,
            message=f"client exited with status {self.exit_code}",
            exit_code=self.exit_code,
        )
