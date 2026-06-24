# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionCommand — the unified inbound command for any ML execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.service.cacheability import is_call_uncacheable


@dataclass(frozen=True)
class RunMlExecutionCommand:
    """The unified input to any ML execution use case.

    ``execution_kind`` selects the execution path — LOCAL_MANAGED dispatches to
    the local client runner, API dispatches to the REST adapter, and
    LOCAL_PASSTHROUGH forwards the opaque ``native_args`` verbatim. The
    ``client`` field names the local adapter (e.g. "claude") for managed runs
    and the provider (e.g. "gemini") for API runs.

    File-system fields (``input_file_paths``, ``allow_paths``, ``scan_trust``,
    ``client_args``, ``grants``) are meaningful only for LOCAL_MANAGED; they
    default to empty/false and are ignored on other kinds.
    ``native_args`` is meaningful only for LOCAL_PASSTHROUGH.
    """

    execution_kind: ExecutionKind
    client: str
    model: str
    effort: str = ""
    context: str = ""
    prompt: str = ""
    user_system_prompt: Optional[str] = None
    input_file_paths: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    scan_trust: bool = False
    client_args: List[str] = field(default_factory=list)
    native_args: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)
    cache_mode: CacheMode = CacheMode.CACHE
    persistence_depth: PersistenceDepth = PersistenceDepth.CACHE
    record_on_error: bool = False
    tags: List[str] = field(default_factory=list)
    session_id: Optional[str] = None

    @property
    def is_uncacheable(self) -> bool:
        if self.execution_kind is ExecutionKind.API:
            return False
        if self.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            return False
        return is_call_uncacheable(self.allow_paths, self.scan_trust)

    def should_persist(self, succeeded: bool) -> bool:
        """Whether this command's policy stores the output for a run that ended
        with ``succeeded``: never below ``CACHE`` depth; a failure only with
        ``record_on_error``."""
        if not self.persistence_depth.stores_output:
            return False
        return succeeded or self.record_on_error
