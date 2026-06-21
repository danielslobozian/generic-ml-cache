# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunManagedLocalExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from generic_ml_cache.application.domain.model.cache_mode import CacheMode


@dataclass(frozen=True)
class RunManagedLocalExecutionCommand:
    """The input to the managed-local use case: raw user intent only.

    It carries file *paths* and raw text, never fingerprints — the use case
    reads the files and computes the fingerprints. The use case builds the
    CallIdentity from this command; the command never builds it itself.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: Optional[str] = None
    input_file_paths: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    scan_trust: bool = False
    client_args: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)
    cache_mode: CacheMode = CacheMode.CACHE
    persist_output: bool = True
    record_on_error: bool = False

    @property
    def is_uncacheable(self) -> bool:
        """Declaring allow-path folders the cache cannot fingerprint makes the
        call non-cacheable — unless the caller takes responsibility with
        ``scan_trust``."""
        return bool(self.allow_paths) and not self.scan_trust

    def should_persist(self, succeeded: bool) -> bool:
        """Whether this command's policy stores an output for a run that ended
        with ``succeeded``: never without ``persist_output``; a failure only with
        ``record_on_error``."""
        if not self.persist_output:
            return False
        return succeeded or self.record_on_error
