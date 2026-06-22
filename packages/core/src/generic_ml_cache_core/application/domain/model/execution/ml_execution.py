# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlExecution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage


@dataclass
class MlExecution:
    """Aggregate root: a demand to run an ML client and what came back.

    The run lifecycle is ``execution_state`` (IN_PROGRESS -> SUCCESS | FAILED).
    The output is a list of ``Artifact`` (stdout, stderr, output files) — there
    is no separate output object and no top-level exit code. A failure's cause
    lives in ``failure`` (present only when FAILED). ``superseded_at`` is the
    cache-currency axis (None = current, set = stale); executions are append-only
    per call identity. ``artifacts`` may be dehydrated (refs only) or hydrated
    (bytes materialised).
    """

    call_identity: CallIdentity
    execution_state: ExecutionState
    execution_kind: ExecutionKind
    output_persisted: bool
    artifacts: List[Artifact] = field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
    failure: Optional[ExecutionFailure] = None
    superseded_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)


def normalize_tags(raw_tags: Iterable[str]) -> List[str]:
    """Normalise user-supplied tags: trim, drop blanks, de-duplicate, sort.

    Tags are metadata, never part of the cache key. Normalising at the boundary
    keeps stored tags deterministic (the same set in any input order compares
    equal) without interpreting their meaning — they are stored verbatim
    otherwise.
    """
    return sorted({tag.strip() for tag in raw_tags if tag and tag.strip()})
