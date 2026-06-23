# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunApiExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.model.run.message import Message


@dataclass(frozen=True)
class RunApiExecutionCommand:
    """The input to the API use case.

    The caller builds the full message list (there is no local client to read
    files or scan folders), so there are no input-file, allow-path, grant, or
    scan-trust fields. An API call is always cacheable.

    Note (future): the ``METER`` depth (storing no output) will be incompatible with
    async execution — an async call must store its output so the caller can retrieve it
    by id later. Async is not built yet, so nothing enforces it here.
    """

    provider: str
    model: str
    messages: List[Message] = field(default_factory=list)
    cache_mode: CacheMode = CacheMode.CACHE
    persistence_depth: PersistenceDepth = PersistenceDepth.CACHE
    record_on_error: bool = False
    session_id: Optional[str] = None

    def should_persist(self, succeeded: bool) -> bool:
        """Whether this command's policy stores the output for a run that ended
        with ``succeeded``: never below ``CACHE`` depth (``METER`` stores nothing);
        a failure only with ``record_on_error``."""
        if not self.persistence_depth.stores_output:
            return False
        return succeeded or self.record_on_error
