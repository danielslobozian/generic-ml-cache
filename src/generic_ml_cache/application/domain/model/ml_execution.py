# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlExecution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.model.execution_output import ExecutionOutput
from generic_ml_cache.application.domain.model.execution_state import ExecutionState
from generic_ml_cache.application.domain.model.token_usage import TokenUsage


@dataclass
class MlExecution:
    """Aggregate root: a demand to run an ML client and what came back.

    Lifecycle: IN_PROGRESS -> SUCCESS | FAILED.
    execution_output and token_usage are absent while IN_PROGRESS.
    output_persisted records whether the output was stored to the blob store.
    """

    call_identity: CallIdentity
    execution_state: ExecutionState
    execution_kind: ExecutionKind
    output_persisted: bool
    execution_output: Optional[ExecutionOutput] = None
    token_usage: Optional[TokenUsage] = None
