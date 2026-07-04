# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CompositeAdapterResolver — try several resolvers in order.

The resolver counterpart to CompositeAdapterCatalog: composition merges the
entry-point resolver with the in-process registry resolver so a registered fake
and an installed adapter resolve through one object. The first resolver that
knows the id wins.
"""

from __future__ import annotations

from collections.abc import Iterable

from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.common.errors import UnknownClient


class CompositeAdapterResolver(AdapterResolverPort):
    """An AdapterResolverPort that delegates to the first resolver that succeeds."""

    def __init__(self, resolvers: Iterable[AdapterResolverPort]) -> None:
        self._resolvers: list[AdapterResolverPort] = list(resolvers)

    def resolve_local_client(
        self,
        adapter_id: str,
        executable_override: str | None = None,
        timeout: float | None = None,
        stream_path: str | None = None,
    ) -> LocalClientPort:
        for resolver in self._resolvers:
            try:
                return resolver.resolve_local_client(
                    adapter_id, executable_override, timeout, stream_path
                )
            except UnknownClient:
                continue
        raise UnknownClient(f"no resolver for id {adapter_id!r}")

    def resolve_runner(self, adapter_id: str) -> MlRunnerPort:
        for resolver in self._resolvers:
            try:
                return resolver.resolve_runner(adapter_id)
            except UnknownClient:
                continue
        raise UnknownClient(f"no resolver for id {adapter_id!r}")
