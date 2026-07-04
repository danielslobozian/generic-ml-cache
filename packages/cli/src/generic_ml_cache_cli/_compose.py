# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CLI composition helpers.

The shared application wiring lives in ``generic_ml_cache_bootstrap`` now; this
module supplies only the CLI's *strategy* — it runs one selected client per
invocation — over the bootstrap composition-root hooks.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from generic_ml_cache_bootstrap.application import build_application_api
from generic_ml_cache_bootstrap.encryption import StoreEncryptionOps
from generic_ml_cache_bootstrap.stub_runners import stub_api_runners
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.usecase.select_adapter_for_execution_service import (
    SelectAdapterForExecutionService,
)
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_cli.discovery import execution_kind_for

ExecutableOverride = Callable[[str], str | None]


def _build_runners(
    catalog: AdapterCatalogPort,
    resolver: AdapterResolverPort,
    client: str | None,
    kind: ExecutionKind | None,
    executable_override: ExecutableOverride | None,
    timeout: float | None,
    stream_path: str | None,
) -> dict[str, RegisteredAdapterPort]:
    # Keyed by client NAME: the service selects the adapter by command.client and
    # dispatches the method by command.execution_kind. The CLI runs one selected
    # client per invocation, so this is a one-entry map.
    if kind is ExecutionKind.LOCAL_MANAGED:
        assert client is not None
        descriptor = SelectAdapterForExecutionService(catalog).select(
            client, ExecutionKind.LOCAL_MANAGED
        )
        exe_override = executable_override(client) if executable_override else None
        # One adapter instance answers both managed and passthrough for this client.
        cli_adapter = cast(
            RegisteredAdapterPort,
            resolver.resolve_local_client(
                descriptor.adapter_id, exe_override, timeout, stream_path
            ),
        )
        return {client: cli_adapter}
    if kind is ExecutionKind.API:
        assert client is not None
        descriptor = SelectAdapterForExecutionService(catalog).select(client, ExecutionKind.API)
        return {client: cast(RegisteredAdapterPort, resolver.resolve_runner(descriptor.adapter_id))}
    # No client selected: stub mode — every API client name is served by the
    # in-process stub adapter (records/replays a canned response, no live call), so
    # demos and cache tests can exercise the pipeline without real credentials.
    return stub_api_runners(catalog)


def build_use_cases(
    store_root: Path,
    executable_override: ExecutableOverride | None = None,
    timeout: float | None = None,
    encryption_token: str | None = None,
    stream_path: str | None = None,
    client: str | None = None,
    max_size: int | None = None,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> ApplicationApi:
    """Wire the application for the CLI: one selected client per invocation."""
    kind = execution_kind_for(client, whitelist) if client is not None else None

    def _runners(
        catalog: AdapterCatalogPort, resolver: AdapterResolverPort
    ) -> dict[str, RegisteredAdapterPort]:
        return _build_runners(
            catalog, resolver, client, kind, executable_override, timeout, stream_path
        )

    return build_application_api(
        store_root,
        _runners,
        encryption_token=encryption_token,
        max_size=max_size,
        whitelist=whitelist,
        client_timeout=timeout,
        diag=diag,
    )


def get_encryption_state(store_root: Path) -> EncryptionState:
    """Return the current encryption state of the store at ``store_root``."""
    return StoreEncryptionOps(store_root).status()
