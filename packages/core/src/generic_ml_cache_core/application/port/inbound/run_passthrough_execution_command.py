# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunPassthroughExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth


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
    persistence_depth: PersistenceDepth = PersistenceDepth.CACHE
    record_on_error: bool = False

    def should_persist(self, succeeded: bool) -> bool:
        """Whether this command's policy stores the output for a run that ended
        with ``succeeded``: never below ``CACHE`` depth (``METER`` stores nothing);
        a failure only with ``record_on_error``."""
        if not self.persistence_depth.stores_output:
            return False
        return succeeded or self.record_on_error
