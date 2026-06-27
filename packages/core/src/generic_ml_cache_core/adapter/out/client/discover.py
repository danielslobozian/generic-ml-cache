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
from typing import Dict, FrozenSet, List, Optional, Tuple, cast

from generic_ml_cache_core.application.port.out.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_core.adapter.registry import (
    get_adapter,
    registered_local_names as registered_names,
)
from generic_ml_cache_core.application.domain.model.client_status import (
    ClientStatus as ClientStatus,
)
from generic_ml_cache_core.application.domain.model.model_listing import (
    ModelListing as ModelListing,
)
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.common.errors import ClientNotFound, UnknownClient


def _probe_version(
    argv: List[str], timeout: float, diag: Optional[DiagnosticsPort] = None
) -> Tuple[Optional[str], Optional[str]]:
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("probe-version ENTER", argv0=argv[0] if argv else "")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure just means "unknown"
        _diag.debug(
            "probe-version FAILED — treating as unknown",
            exc=exc,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return None, f"version check failed: {exc}"
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    version = first or None
    detail = None if first else "no version output"
    _diag.debug(
        "probe-version EXIT",
        version=version,
        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
    )
    return version, detail


def probe(
    name: str,
    executable: Optional[str] = None,
    timeout: float = 10.0,
    diag: Optional[DiagnosticsPort] = None,
) -> ClientStatus:
    """Probe one registered client: is its executable present, and what version?

    Never raises for an absent client -- absence is reported in the result.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("probe ENTER", name=name)
    adapter = cast(ClientAdapter, get_adapter(name))
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        result = ClientStatus(name=name, present=False, detail=str(exc))
        _diag.debug(
            "probe EXIT",
            name=name,
            present=False,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return result
    version, detail = _probe_version(adapter.version_argv(exe), timeout, diag=_diag)
    result = ClientStatus(name=name, present=True, executable=exe, version=version, detail=detail)
    _diag.debug(
        "probe EXIT",
        name=name,
        present=True,
        version=version,
        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
    )
    return result


def probe_all(
    timeout: float = 10.0,
    executables: Optional[Dict[str, str]] = None,
    whitelist: Optional[FrozenSet[str]] = None,
    diag: Optional[DiagnosticsPort] = None,
) -> List[ClientStatus]:
    """Probe every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to probe
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("probe-all ENTER")
    exe = executables or {}
    results = [
        probe(name, executable=exe.get(name), timeout=timeout, diag=_diag)
        for name in registered_names(whitelist=whitelist)
    ]
    _diag.debug(
        "probe-all EXIT",
        count=len(results),
        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
    )
    return results


def list_models(
    name: str,
    executable: Optional[str] = None,
    timeout: float = 30.0,
    whitelist: Optional[FrozenSet[str]] = None,
    diag: Optional[DiagnosticsPort] = None,
) -> ModelListing:
    """List one client's models by relaying its own listing command.

    Never raises for an absent client or a client that cannot enumerate; both
    are reported in the result. A relayed list reflects what the *authenticated*
    client can reach, which is why it is preferred over any static catalog.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("list-models ENTER", name=name)
    adapter = get_adapter(name, whitelist=whitelist)
    if not isinstance(adapter, ClientAdapter):
        raise UnknownClient(f"not a local managed adapter: {name!r}")
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        result = ModelListing(name=name, present=False, supported=False, reason=str(exc))
        _diag.debug(
            "list-models EXIT",
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
        _diag.debug(
            "list-models EXIT",
            name=name,
            supported=False,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return result

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure is just "couldn't list"
        _diag.debug(
            "list-models launch failed",
            name=name,
            exc=exc,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        result = ModelListing(
            name=name, present=True, supported=True, reason=f"model listing failed: {exc}"
        )
        _diag.debug(
            "list-models EXIT",
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
        _diag.debug(
            "list-models EXIT",
            name=name,
            returncode=proc.returncode,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return result

    result = ModelListing(
        name=name, present=True, supported=True, models=adapter.parse_model_list(proc.stdout)
    )
    _diag.debug(
        "list-models EXIT",
        name=name,
        model_count=len(result.models) if result.models else 0,
        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
    )
    return result


def list_models_all(
    timeout: float = 30.0,
    executables: Optional[Dict[str, str]] = None,
    whitelist: Optional[FrozenSet[str]] = None,
    diag: Optional[DiagnosticsPort] = None,
) -> List[ModelListing]:
    """List models for every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to use
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("list-models-all ENTER")
    exe = executables or {}
    results = [
        list_models(
            name, executable=exe.get(name), timeout=timeout, whitelist=whitelist, diag=_diag
        )
        for name in registered_names(whitelist=whitelist)
    ]
    _diag.debug(
        "list-models-all EXIT",
        count=len(results),
        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
    )
    return results
