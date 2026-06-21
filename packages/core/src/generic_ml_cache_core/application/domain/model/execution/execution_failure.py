# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionFailure and FailureReason."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class FailureReason(enum.Enum):
    """Why a run failed. Starts minimal; grows as features land (TIMEOUT,
    NETWORK, CLIENT_ERROR, …)."""

    NONZERO_EXIT = "nonzero_exit"


@dataclass(frozen=True)
class ExecutionFailure:
    """The interpreted cause of a failed run — present only when the execution
    state is FAILED.

    Separate from stderr (captured output, an Artifact): this is *why* it failed.
    It generalises across local and API executions — ``exit_code`` is the local
    client's code when that is the cause, and ``None`` for an API failure whose
    cause has no exit code.
    """

    reason: FailureReason
    message: str
    exit_code: Optional[int] = None
