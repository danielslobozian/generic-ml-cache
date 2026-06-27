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
from typing import Dict, FrozenSet, List, Optional, Tuple, cast

from generic_ml_cache_core.adapter.registry import (
    get_adapter,
    registered_local_names as registered_names,
)
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.application.domain.model.client_status import (
    ClientStatus as ClientStatus,
)
from generic_ml_cache_core.application.domain.model.model_listing import (
    ModelListing as ModelListing,
)
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.common.errors import ClientNotFound, UnknownClient


def _probe_version(argv: List[str], timeout: float) -> Tuple[Optional[str], Optional[str]]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure just means "unknown"
        return None, f"version check failed: {exc}"
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    return (first or None), (None if first else "no version output")


def probe(name: str, executable: Optional[str] = None, timeout: float = 10.0) -> ClientStatus:
    """Probe one registered client: is its executable present, and what version?

    Never raises for an absent client -- absence is reported in the result.
    """
    adapter = cast(ClientAdapter, get_adapter(name))
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        return ClientStatus(name=name, present=False, detail=str(exc))
    version, detail = _probe_version(adapter.version_argv(exe), timeout)
    return ClientStatus(name=name, present=True, executable=exe, version=version, detail=detail)


def probe_all(
    timeout: float = 10.0,
    executables: Optional[Dict[str, str]] = None,
    whitelist: Optional[FrozenSet[str]] = None,
) -> List[ClientStatus]:
    """Probe every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to probe
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    exe = executables or {}
    return [
        probe(name, executable=exe.get(name), timeout=timeout)
        for name in registered_names(whitelist=whitelist)
    ]


def list_models(
    name: str,
    executable: Optional[str] = None,
    timeout: float = 30.0,
    whitelist: Optional[FrozenSet[str]] = None,
) -> ModelListing:
    """List one client's models by relaying its own listing command.

    Never raises for an absent client or a client that cannot enumerate; both
    are reported in the result. A relayed list reflects what the *authenticated*
    client can reach, which is why it is preferred over any static catalog.
    """
    adapter = get_adapter(name, whitelist=whitelist)
    if not isinstance(adapter, ClientAdapter):
        raise UnknownClient(f"not a local managed adapter: {name!r}")
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        return ModelListing(name=name, present=False, supported=False, reason=str(exc))

    argv = adapter.models_argv(exe)
    if argv is None:
        return ModelListing(
            name=name,
            present=True,
            supported=False,
            reason="this client has no model-listing command",
        )

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure is just "couldn't list"
        return ModelListing(
            name=name, present=True, supported=True, reason=f"model listing failed: {exc}"
        )

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err[0].strip() if err else f"exit {proc.returncode}"
        return ModelListing(
            name=name,
            present=True,
            supported=True,
            reason=f"client exited {proc.returncode}: {detail}",
        )

    return ModelListing(
        name=name, present=True, supported=True, models=adapter.parse_model_list(proc.stdout)
    )


def list_models_all(
    timeout: float = 30.0,
    executables: Optional[Dict[str, str]] = None,
    whitelist: Optional[FrozenSet[str]] = None,
) -> List[ModelListing]:
    """List models for every registered client, in name order.

    ``executables`` optionally maps a client name to the executable to use
    (e.g. from the ``[executables]`` config); a client absent from the mapping
    falls back to its adapter's own ``PATH`` lookup.
    ``whitelist`` restricts which adapters are considered active.
    """
    exe = executables or {}
    return [
        list_models(name, executable=exe.get(name), timeout=timeout, whitelist=whitelist)
        for name in registered_names(whitelist=whitelist)
    ]
