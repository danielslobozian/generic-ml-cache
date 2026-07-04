# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterResolverPort — turn a chosen adapter id into a runnable adapter.

The catalog answers "what exists?"; the resolver answers "give me the
implementation." Keeping them apart means availability/selection never has to
instantiate a real adapter. The resolver is infrastructure (it loads and
constructs concrete classes); core only depends on this port.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.outbound.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort


class AdapterResolverPort(ABC):
    """Resolve an ``adapter_id`` (from a descriptor) to a concrete adapter."""

    @abstractmethod
    def resolve_local_client(
        self,
        adapter_id: str,
        executable_override: str | None = None,
        timeout: float | None = None,
        stream_path: str | None = None,
    ) -> LocalClientPort:
        """Construct the local CLI client adapter for ``adapter_id`` with the given
        per-run config (PATH override, subprocess timeout, live-stream path)."""

    @abstractmethod
    def resolve_runner(self, adapter_id: str) -> MlRunnerPort:
        """Construct the API runner adapter for ``adapter_id`` (no per-run config)."""
