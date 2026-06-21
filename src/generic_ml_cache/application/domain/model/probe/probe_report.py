# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ProbeReport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic_ml_cache.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache.application.domain.model.probe.probe_status import ProbeStatus


@dataclass(frozen=True)
class ProbeReport:
    """What a read-only probe forecasts for a call.

    ``execution_key`` is derived for every verdict (so a caller can show the key
    even on a miss). ``execution`` is the dehydrated current execution on a HIT —
    present only then — carrying the queryable metadata (artifacts, usage) without
    fetching any output bytes.
    """

    status: ProbeStatus
    execution_key: str
    execution: Optional[MlExecution] = None
