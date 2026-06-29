# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterResolverPort — turn a chosen adapter id into a runnable adapter.

The catalog answers "what exists?"; the resolver answers "give me the
implementation." Keeping them apart means availability/selection never has to
instantiate a real adapter. The resolver is infrastructure (it loads and
constructs concrete classes); core only depends on this port.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from generic_ml_cache_core.application.port.out.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort


@runtime_checkable
class AdapterResolverPort(Protocol):
    """Resolve an ``adapter_id`` (from a descriptor) to a concrete adapter."""

    def resolve_local_client(
        self,
        adapter_id: str,
        executable_override: Optional[str] = None,
        timeout: Optional[float] = None,
        stream_path: Optional[str] = None,
    ) -> LocalClientPort:
        """Construct the local CLI client adapter for ``adapter_id`` with the given
        per-run config (PATH override, subprocess timeout, live-stream path)."""
        ...

    def resolve_runner(self, adapter_id: str) -> MlRunnerPort:
        """Construct the API runner adapter for ``adapter_id`` (no per-run config)."""
        ...
