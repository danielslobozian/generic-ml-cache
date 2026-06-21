# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunPassthroughExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from generic_ml_cache.application.domain.model.cache_mode import CacheMode


@dataclass(frozen=True)
class RunPassthroughExecutionCommand:
    """The input to the passthrough use case.

    Everything after the client name is opaque: ``native_args`` is forwarded to
    the client verbatim and enters the key as-is (by fingerprint). A passthrough
    is always cacheable (it declares no scan folders), so there is no allow-path
    or scan-trust here.
    """

    client: str
    native_args: List[str] = field(default_factory=list)
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
