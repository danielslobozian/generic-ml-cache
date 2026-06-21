# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionState."""

from __future__ import annotations

import enum


class ExecutionState(enum.Enum):
    """Lifecycle state of an MlExecution.

    Transitions: IN_PROGRESS -> SUCCESS | FAILED.

    PASSTHROUGH is not a state — it is an ExecutionKind. A passthrough
    execution has the same IN_PROGRESS -> SUCCESS | FAILED lifecycle.
    """

    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
