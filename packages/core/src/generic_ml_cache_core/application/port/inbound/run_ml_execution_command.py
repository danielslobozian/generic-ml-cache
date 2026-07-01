# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionCommand — the unified inbound command for any ML execution."""

from __future__ import annotations

from dataclasses import dataclass

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
    user_system_prompt: str | None = None
    input_file_paths: tuple[str, ...] = ()
    allow_paths: tuple[str, ...] = ()
    scan_trust: bool = False
    client_args: tuple[str, ...] = ()
    native_args: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()
    cache_mode: CacheMode = CacheMode.CACHE
    persistence_depth: PersistenceDepth = PersistenceDepth.CACHE
    record_on_error: bool = False
    tags: tuple[str, ...] = ()
    session_id: str | None = None

    def __post_init__(self) -> None:
        # Accept any iterable input (a parser hands lists) but store immutably, so
        # this keyed command is deeply stable and hashable.
        for name in (
            "input_file_paths",
            "allow_paths",
            "client_args",
            "native_args",
            "grants",
            "tags",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))

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
