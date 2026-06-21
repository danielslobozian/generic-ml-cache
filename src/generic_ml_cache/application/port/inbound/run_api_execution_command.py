# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunApiExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.domain.model.message import Message


@dataclass(frozen=True)
class RunApiExecutionCommand:
    """The input to the API use case.

    The caller builds the full message list (there is no local client to read
    files or scan folders), so there are no input-file, allow-path, grant, or
    scan-trust fields. An API call is always cacheable.

    Note (future): ``persist_output = False`` will be incompatible with async
    execution — an async call must store its output so the caller can retrieve it
    by id later. Async is not built yet, so nothing enforces it here.
    """

    provider: str
    model: str
    messages: List[Message] = field(default_factory=list)
    cache_mode: CacheMode = CacheMode.CACHE
    persist_output: bool = True
    record_on_error: bool = False

    def should_persist(self, succeeded: bool) -> bool:
        """Whether this command's policy stores an output for a run that ended
        with ``succeeded``: never without ``persist_output``; a failure only with
        ``record_on_error``."""
        if not self.persist_output:
            return False
        return succeeded or self.record_on_error
