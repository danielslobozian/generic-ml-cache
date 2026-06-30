# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client discovery: report which configured clients are present and runnable.

This is **read-only and advisory**. Discovery never chooses a client, never
restricts which model may run, and never gates a call -- it only reports what it
found on this machine. The run is always the validator.

It is the detection half of "detection, not selection": the cache can tell a
caller *what is here*; deciding *what to use* stays with the caller.
"""

from __future__ import annotations

import subprocess
import time

from generic_ml_cache_core.application.domain.model.client_status import (
    ClientStatus as ClientStatus,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.model_listing import (
    ModelListing as ModelListing,
)
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.local_client_port import LocalClientPort
from generic_ml_cache_core.common.errors import ClientNotFound, UnknownClient

from generic_ml_cache_adapters.discovery.composition import (
    catalog_for,
    default_resolver,
    registered_local_names,
)

_LIST_MODELS_EXIT = "list-models EXIT"


def _resolve_local_client(name: str, whitelist: frozenset[str] | None = None) -> LocalClientPort:
    """Resolve a local-managed client adapter by client name, via the catalog +
    resolver. Raises :class:`UnknownClient` if no local adapter serves ``name``."""
    descriptors = list(catalog_for(whitelist).find_by_client_name(name))
    if not descriptors:
        raise UnknownClient(f"unknown adapter {name!r}")
    local = [d for d in descriptors if d.supports_mode(ExecutionKind.LOCAL_MANAGED)]
    if not local:
        raise UnknownClient(f"not a local managed adapter: {name!r}")
    return default_resolver().resolve_local_client(local[0].adapter_id)


def _probe_version(
    argv: list[str], timeout: float, diag: DiagnosticsPort | None = None
) -> tuple[str | None, str | None]:
    _t = time.perf_counter()
    if diag:
        diag.debug("probe-version ENTER", argv0=argv[0] if argv else "")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure just means "unknown"
        if diag:
            diag.debug(
                "probe-version FAILED — treating as unknown",
                exc=exc,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return None, f"version check failed: {exc}"
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    version = first or None
    detail = None if first else "no version output"
    if diag:
        diag.debug(
            "probe-version EXIT",
            version=version,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
    return version, detail


def probe(
    name: str,
    executable: str | None = None,
    timeout: float = 10.0,
    diag: DiagnosticsPort | None = None,
) -> ClientStatus:
    """Probe one registered client: is its executable present, and what version?

    Never raises for an absent client -- absence is reported in the result.
    """
    _t = time.perf_counter()
    if diag:
        diag.debug("probe ENTER", name=name)
    adapter = _resolve_local_client(name)
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        result = ClientStatus(name=name, present=False, detail=str(exc))
        if diag:
            diag.debug(
                "probe EXIT",
                name=name,
                present=False,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result
    version, detail = _probe_version(adapter.version_argv(exe), timeout, diag=diag)
    result = ClientStatus(name=name, present=True, executable=exe, version=version, detail=detail)
    if diag:
        diag.debug(
            "probe EXIT",
            name=name,
            present=True,
            version=version,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
    return result


def probe_all(
    timeout: float = 10.0,
    executables: dict[str, str] | None = None,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> list[ClientStatus]:
    """Probe every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to probe
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    _t = time.perf_counter()
    if diag:
        diag.debug("probe-all ENTER")
    exe = executables or {}
    results = [
        probe(name, executable=exe.get(name), timeout=timeout, diag=diag)
        for name in registered_local_names(whitelist)
    ]
    if diag:
        diag.debug(
            "probe-all EXIT",
            count=len(results),
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
    return results


def list_models(  # noqa: C901
    name: str,
    executable: str | None = None,
    timeout: float = 30.0,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> ModelListing:
    """List one client's models by relaying its own listing command.

    Never raises for an absent client or a client that cannot enumerate; both
    are reported in the result. A relayed list reflects what the *authenticated*
    client can reach, which is why it is preferred over any static catalog.
    """
    _t = time.perf_counter()
    if diag:
        diag.debug("list-models ENTER", name=name)
    adapter = _resolve_local_client(name, whitelist)
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        result = ModelListing(name=name, present=False, supported=False, reason=str(exc))
        if diag:
            diag.debug(
                _LIST_MODELS_EXIT,
                name=name,
                present=False,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    argv = adapter.models_argv(exe)
    if argv is None:
        result = ModelListing(
            name=name,
            present=True,
            supported=False,
            reason="this client has no model-listing command",
        )
        if diag:
            diag.debug(
                _LIST_MODELS_EXIT,
                name=name,
                supported=False,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure is just "couldn't list"
        if diag:
            diag.debug(
                "list-models launch failed",
                name=name,
                exc=exc,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        result = ModelListing(
            name=name, present=True, supported=True, reason=f"model listing failed: {exc}"
        )
        if diag:
            diag.debug(
                _LIST_MODELS_EXIT,
                name=name,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err[0].strip() if err else f"exit {proc.returncode}"
        result = ModelListing(
            name=name,
            present=True,
            supported=True,
            reason=f"client exited {proc.returncode}: {detail}",
        )
        if diag:
            diag.debug(
                _LIST_MODELS_EXIT,
                name=name,
                returncode=proc.returncode,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    result = ModelListing(
        name=name, present=True, supported=True, models=adapter.parse_model_list(proc.stdout)
    )
    if diag:
        diag.debug(
            "list-models EXIT",
            name=name,
            model_count=len(result.models) if result.models else 0,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
    return result


def list_models_all(
    timeout: float = 30.0,
    executables: dict[str, str] | None = None,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> list[ModelListing]:
    """List models for every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to use
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    _t = time.perf_counter()
    if diag:
        diag.debug("list-models-all ENTER")
    exe = executables or {}
    results = [
        list_models(name, executable=exe.get(name), timeout=timeout, whitelist=whitelist, diag=diag)
        for name in registered_local_names(whitelist)
    ]
    if diag:
        diag.debug(
            "list-models-all EXIT",
            count=len(results),
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
    return results
