# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Default adapter-catalog composition, shared by the CLI and daemon drivers.

The recommended default wiring: entry-point adapters merged with any in-process
registered adapters, as a live catalog and resolver. Drivers opt into this (they
could compose differently) and add deployment policy such as a whitelist on top.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_bootstrap.discovery.composite_adapter_catalog import CompositeAdapterCatalog
from generic_ml_cache_bootstrap.discovery.composite_adapter_resolver import CompositeAdapterResolver
from generic_ml_cache_bootstrap.discovery.entrypoint_adapter_catalog import EntryPointAdapterCatalog
from generic_ml_cache_bootstrap.discovery.entrypoint_adapter_resolver import (
    EntryPointAdapterResolver,
)
from generic_ml_cache_bootstrap.discovery.in_memory_adapter_registry import default_registry

_PRIMARY_MODE = {
    AdapterBoundary.LOCAL_CLI: ExecutionKind.LOCAL_MANAGED,
    AdapterBoundary.API: ExecutionKind.API,
}

_entrypoint_catalog: EntryPointAdapterCatalog | None = None
_catalog: CompositeAdapterCatalog | None = None
_resolver: CompositeAdapterResolver | None = None


def _entrypoint() -> EntryPointAdapterCatalog:
    global _entrypoint_catalog
    if _entrypoint_catalog is None:
        _entrypoint_catalog = EntryPointAdapterCatalog()
    return _entrypoint_catalog


def default_catalog() -> AdapterCatalogPort:
    """Entry-point adapters merged with the in-process registry (a live view)."""
    global _catalog
    if _catalog is None:
        _catalog = CompositeAdapterCatalog([_entrypoint(), default_registry()])
    return _catalog


def default_resolver() -> AdapterResolverPort:
    """Resolve an adapter id from the DEFAULT (trusted-only) catalog's vetted classes
    or the in-process registry. Bound to the same entry-point catalog as
    :func:`default_catalog`, so it constructs only adapters that catalog gated in
    (X15) — never by re-loading an ungated plugin."""
    global _resolver
    if _resolver is None:
        _resolver = CompositeAdapterResolver(
            [EntryPointAdapterResolver(_entrypoint()), default_registry()]
        )
    return _resolver


def catalog_and_resolver_for(
    whitelist: frozenset[str] | None = None,
) -> tuple[AdapterCatalogPort, AdapterResolverPort]:
    """A catalog and a resolver that SHARE one gated entry-point catalog, so the
    resolver constructs exactly the adapters the catalog vetted — one trust gate, one
    place (X15). Use this whenever a caller both lists and resolves under the same
    ``whitelist``, so listing and resolution can never diverge."""
    if whitelist is None:
        return default_catalog(), default_resolver()
    entrypoint = EntryPointAdapterCatalog(whitelist=whitelist)
    registry = default_registry()
    return (
        CompositeAdapterCatalog([entrypoint, registry]),
        CompositeAdapterResolver([EntryPointAdapterResolver(entrypoint), registry]),
    )


def catalog_for(whitelist: frozenset[str] | None = None) -> AdapterCatalogPort:
    """The default catalog.

    ``whitelist`` opts third-party plugins (by entry-point name) into loading;
    the bundled adapters always load. With no whitelist, only the trusted bundled
    adapters plus any in-process registrations are visible — the safe default
    (a package installed for another reason never silently becomes a client).
    """
    if whitelist is None:
        return default_catalog()
    entrypoint = EntryPointAdapterCatalog(whitelist=whitelist)
    return CompositeAdapterCatalog([entrypoint, default_registry()])


def _unknown_adapter(name: str, catalog: AdapterCatalogPort) -> UnknownClient:
    known = ", ".join(sorted({d.client_name for d in catalog.list_adapters()})) or "(none)"
    return UnknownClient(f"unknown adapter {name!r}; available: {known}")


def get_adapter(name: str, whitelist: frozenset[str] | None = None) -> object:
    """Resolve a constructed adapter by client name (a local client or an API
    runner). A convenience over the catalog + resolver; raises :class:`UnknownClient`
    if the client is absent. Lives here, in infrastructure — never in core."""
    catalog, resolver = catalog_and_resolver_for(whitelist)
    descriptors = catalog.find_by_client_name(name)
    if not descriptors:
        raise _unknown_adapter(name, catalog)
    descriptor = descriptors[0]
    if descriptor.boundary is AdapterBoundary.API:
        return resolver.resolve_runner(descriptor.adapter_id)
    return resolver.resolve_local_client(descriptor.adapter_id)


def execution_kind_for(client: str, whitelist: frozenset[str] | None = None) -> ExecutionKind:
    """The primary execution kind for a client (LOCAL_MANAGED for a CLI, API for a
    provider). Raises :class:`UnknownClient` if the client is absent."""
    catalog = catalog_for(whitelist)
    descriptors = catalog.find_by_client_name(client)
    if not descriptors:
        raise _unknown_adapter(client, catalog)
    return _PRIMARY_MODE[descriptors[0].boundary]


def registered_names(whitelist: frozenset[str] | None = None) -> list[str]:
    return sorted({d.client_name for d in catalog_for(whitelist).list_adapters()})


def registered_local_names(whitelist: frozenset[str] | None = None) -> list[str]:
    return sorted(
        {
            d.client_name
            for d in catalog_for(whitelist).list_adapters()
            if d.supports_mode(ExecutionKind.LOCAL_MANAGED)
        }
    )


def adapter_sources(whitelist: frozenset[str] | None = None) -> dict[str, str]:
    """Map each entry-point client name to the distribution that provided it."""
    sources = _entrypoint().sources()  # adapter_id -> "<package> <version>"
    visible = {d.client_name for d in catalog_for(whitelist).list_adapters()}
    out: dict[str, str] = {}
    for descriptor in _entrypoint().list_adapters():
        if descriptor.client_name in visible and descriptor.adapter_id in sources:
            out[descriptor.client_name] = sources[descriptor.adapter_id]
    return out
