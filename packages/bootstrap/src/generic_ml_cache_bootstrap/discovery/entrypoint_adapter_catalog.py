# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EntryPointAdapterCatalog — discover adapters from installed entry points.

The default catalog: it scans the ``gmlcache.adapters`` entry-point group, loads
each adapter class, and reads its ``descriptor()`` — without instantiating the
adapter. A broken or incompatible entry point is warned and skipped; bad
third-party code never crashes discovery. This is where the packaging-system
dependency lives, out of core.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import cast

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.adapter_catalog_port import AdapterCatalogPort

from generic_ml_cache_bootstrap.discovery._entrypoints import (
    ADAPTER_CONTRACT_VERSION,
    ADAPTER_ENTRYPOINT_GROUP,
    describe_source,
    distribution_name,
    iter_entry_points,
)

# Distributions whose plugins are trusted to load by default. The bundled
# adapters ship here; any other distribution declaring a gmlcache.adapters
# entry point is third-party and must be whitelisted by name to load (its module
# code runs at ep.load(), so the gate is BEFORE the load — ambient authority).
DEFAULT_TRUSTED_DISTRIBUTIONS = frozenset({"generic-ml-cache-adapters"})


class EntryPointAdapterCatalog(AdapterCatalogPort):
    """Catalog backed by the installed ``gmlcache.adapters`` entry points.

    Trusted-distribution plugins always load. A third-party plugin loads only if
    its entry-point name is in ``whitelist`` — otherwise it is never imported, so
    a package installed for another reason cannot silently become a cache client.
    """

    def __init__(
        self,
        group: str = ADAPTER_ENTRYPOINT_GROUP,
        *,
        whitelist: frozenset[str] | None = None,
        trusted_distributions: frozenset[str] = DEFAULT_TRUSTED_DISTRIBUTIONS,
    ) -> None:
        self._group = group
        self._whitelist = whitelist
        self._trusted = trusted_distributions
        self._descriptors: list[AdapterDescriptor] | None = None
        self._sources: dict[str, str] = {}

    def _is_allowed_to_load(self, ep: object) -> bool:
        """Trust gate, evaluated BEFORE ep.load(): a trusted distribution always
        loads; anything else only if its entry-point name is whitelisted."""
        if distribution_name(ep) in self._trusted:
            return True
        ep_name = getattr(ep, "name", "")
        return self._whitelist is not None and ep_name in self._whitelist

    def _scan(self) -> list[AdapterDescriptor]:
        descriptors: list[AdapterDescriptor] = []
        for ep in iter_entry_points(self._group):
            ep_key = getattr(ep, "name", str(ep))
            if not self._is_allowed_to_load(ep):
                # Untrusted third-party, not whitelisted: never import it.
                continue
            try:
                cls = ep.load()
            except Exception as exc:  # noqa: BLE001 — broken plugin must not crash discovery
                warnings.warn(
                    f"gmlcache: could not load entry-point adapter {ep_key!r}: {exc}", stacklevel=2
                )
                continue

            declared = getattr(cls, "adapter_contract_version", None)
            if declared is not None and declared != ADAPTER_CONTRACT_VERSION:
                warnings.warn(
                    f"gmlcache: entry-point adapter {ep_key!r} targets contract {declared!r} "
                    f"but this core requires {ADAPTER_CONTRACT_VERSION!r}; skipping",
                    stacklevel=2,
                )
                continue

            describe = getattr(cls, "descriptor", None)
            if not callable(describe):
                warnings.warn(
                    f"gmlcache: entry-point adapter {ep_key!r} has no descriptor(); skipping",
                    stacklevel=2,
                )
                continue
            try:
                descriptor = cast(AdapterDescriptor, describe())
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    f"gmlcache: descriptor() failed for entry-point adapter {ep_key!r}: {exc}",
                    stacklevel=2,
                )
                continue

            descriptors.append(descriptor)
            self._sources[descriptor.adapter_id] = describe_source(ep)
        return descriptors

    def _ensure_loaded(self) -> list[AdapterDescriptor]:
        if self._descriptors is None:
            self._descriptors = self._scan()
        return self._descriptors

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        return list(self._ensure_loaded())

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        return [d for d in self._ensure_loaded() if d.client_name == client_name]

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return any(
            d.client_name == client_name and d.supports_mode(mode) for d in self._ensure_loaded()
        )

    def sources(self) -> dict[str, str]:
        """Map each ``adapter_id`` to the distribution that provided it (for doctor)."""
        self._ensure_loaded()
        return dict(self._sources)
