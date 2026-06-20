# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The cache core: tie together store + adapter + isolation under three modes.

Modes
-----
offline : never call real; serve from cache; **miss -> error**. The former
          "mock": a knowing switch to replay-only.
cache   : (default) hit -> serve; miss -> call real, record, serve.
refresh : always call real, overwrite the cassette.

On both a hit and a fresh recording the cache *applies* the response so the
caller observes the same effect either way: captured files are written into the
caller's output folder, and stdout/stderr/exit are reproduced.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import access_registry
from .adapters.registry import get_adapter
from .cassette import Cassette, Response
from .common.errors import CacheMiss
from .isolation import record_real_call
from .mode import Mode as Mode
from .outcome import Outcome as Outcome
from .probe_result import ProbeResult as ProbeResult
from .probe_status import ProbeStatus as ProbeStatus
from .request import Request as Request
from .store import CassetteStore


def probe(
    request: Request,
    store: CassetteStore,
    trust_scan: bool = False,
) -> ProbeResult:
    """Answer "is this exact call already cached?" -- read-only, side-effect-free.

    A probe is a *forecast*, not a run: it launches no client, writes no cassette,
    and records no access event. It exists so a caller (the workflow engine) can
    ask which calls would hit and which would miss *before* committing to a run.

    Correctness rests on reusing run's own machinery rather than reimplementing it:
    the cacheability test is the same :attr:`Request.requires_passthrough` /
    ``trust_scan`` rule :func:`_resolve` applies, and the lookup is the same
    ``store.lookup`` over the same :attr:`Request.input_data`, so the key derived
    here is byte-for-byte the key a ``run`` would derive. If that logic ever
    changes, both paths change together.

    The three verdicts mirror what a ``cache``-mode run would do with this call:
    - ``NON_CACHEABLE`` -- declares allow-path folders the cache cannot fingerprint
      (and scan-trust is off), so a run would pass through and store nothing; a
      probe therefore never reports it cached.
    - ``HIT`` -- a cassette exists; a run would serve it.
    - ``MISS`` -- cacheable, but nothing recorded yet; a run would record.

    The verdict is about cache *state*, not run *mode*: it is independent of
    offline/cache/refresh, which are run-time policies rather than questions about
    whether a recording exists.
    """
    if request.requires_passthrough and not trust_scan:
        return ProbeResult(status=ProbeStatus.NON_CACHEABLE)

    existing = store.lookup(request.client, request.model, request.effort, request.input_data)
    if existing is None:
        return ProbeResult(status=ProbeStatus.MISS)
    return ProbeResult(status=ProbeStatus.HIT, cassette=existing)


def resolve(
    request: Request,
    store: CassetteStore,
    mode: Mode = Mode.CACHE,
    executable: Optional[str] = None,
    timeout: Optional[float] = None,
    trust_scan: bool = False,
    record_on_error: bool = False,
    stream_path: Optional[str] = None,
) -> Outcome:
    """Resolve a request and record one access event for observability.

    Thin wrapper over the resolution logic: it runs the resolve, then logs exactly
    one access event (hit / record / miss) to the store's non-load-bearing
    registry — a passthrough call logs nothing (it is outside cache accounting),
    and an offline miss logs a miss before the error propagates. Registry writes
    are best-effort and never affect the result. See ``_resolve`` for the full
    mode and storage semantics.
    """
    try:
        outcome = _resolve(
            request,
            store,
            mode,
            executable=executable,
            timeout=timeout,
            trust_scan=trust_scan,
            record_on_error=record_on_error,
            stream_path=stream_path,
        )
    except CacheMiss:
        _record_access(store, access_registry.MISS, request, None)
        raise
    event = _event_for(outcome)
    if event is not None:
        _record_access(store, event, request, outcome.cassette)
    return outcome


def _event_for(outcome: "Outcome") -> Optional[str]:
    if outcome.hit:
        return access_registry.HIT
    if outcome.recorded:
        return access_registry.RECORD
    if outcome.failed_unstored:
        return access_registry.MISS
    return None  # passthrough: ran fresh, not part of hit/miss accounting


def _record_access(
    store: CassetteStore, event: str, request: Request, cassette: Optional[Cassette]
) -> None:
    store.registry.record(
        event,
        match_key=cassette.match_key if cassette is not None else None,
        client=request.client,
        model=request.model,
        effort=request.effort,
    )


def _resolve(
    request: Request,
    store: CassetteStore,
    mode: Mode = Mode.CACHE,
    executable: Optional[str] = None,
    timeout: Optional[float] = None,
    trust_scan: bool = False,
    record_on_error: bool = False,
    stream_path: Optional[str] = None,
) -> Outcome:
    """Resolve a request against the store under ``mode`` (no I/O to caller).

    A call that declares ``allow_paths`` reads folders the cache cannot
    fingerprint, so by default it is **passthrough**: it always runs fresh and
    stores nothing (no hit is ever served for it). ``trust_scan`` is the explicit,
    opt-in override that lets such a call be cached anyway (the caller asserts the
    folders are stable); it is wired here but not yet exposed.

    A real call that **fails** (non-zero exit) is, by default, **not stored**: a
    failure is usually transient (a bad model id, an auth hiccup, a rate limit), so
    caching it would replay the failure forever and a retry could never reach the
    real client. The caller still receives the real failed response; it simply is
    not written to the store, so the next identical call runs fresh.
    ``record_on_error=True`` opts into storing failures as well (the VCR
    ``record_on_error`` convention) -- for the cases where a deterministic failure
    *is* the result worth replaying. A refresh whose fresh call fails leaves any
    existing cassette untouched rather than overwriting a good recording with a bad
    one.
    """
    adapter = get_adapter(request.client)

    if request.requires_passthrough and not trust_scan:
        # Unfingerprintable folders -> never cached: run fresh, store nothing.
        if mode is Mode.OFFLINE:
            raise CacheMiss(
                "offline: this call declares allow-path folders the cache cannot "
                "fingerprint, so it is never cached and cannot be served offline. "
                "Run it online, or drop the allow-path folders."
            )
        resolved_exe = adapter.resolve_executable(executable)
        result = record_real_call(
            adapter=adapter,
            executable=resolved_exe,
            model=request.model,
            effort=request.effort,
            context=request.context,
            prompt=request.prompt,
            user_system_prompt=request.user_system_prompt,
            timeout=timeout,
            allowed_read_paths=request.allowed_read_paths,
            add_dir_paths=request.add_dir_paths,
            client_args=request.client_args,
            grants=request.grants,
            stream_path=stream_path,
        )
        cassette = Cassette(
            client=request.client,
            model=request.model,
            effort=request.effort,
            input_data=request.input_data,
            response=result.response,
        )
        # Deliberately NOT stored.
        return Outcome(
            result.response, hit=False, recorded=False, cassette=cassette, passthrough=True
        )

    existing = store.lookup(request.client, request.model, request.effort, request.input_data)

    if mode is Mode.OFFLINE:
        if existing is None:
            from .common.checksum import checksum_input_data

            raise CacheMiss(
                "offline miss: no cassette for "
                f"client={request.client!r} model={request.model!r} "
                f"effort={request.effort!r} "
                f"checksum={checksum_input_data(request.input_data)}"
            )
        return Outcome(existing.response, hit=True, recorded=False, cassette=existing)

    if mode is Mode.CACHE and existing is not None:
        return Outcome(existing.response, hit=True, recorded=False, cassette=existing)

    # CACHE-miss or REFRESH: make the real call and record it.
    resolved_exe = adapter.resolve_executable(executable)
    result = record_real_call(
        adapter=adapter,
        executable=resolved_exe,
        model=request.model,
        effort=request.effort,
        context=request.context,
        prompt=request.prompt,
        user_system_prompt=request.user_system_prompt,
        timeout=timeout,
        allowed_read_paths=request.allowed_read_paths,
        add_dir_paths=request.add_dir_paths,
        client_args=request.client_args,
        grants=request.grants,
        stream_path=stream_path,
    )
    cassette = Cassette(
        client=request.client,
        model=request.model,
        effort=request.effort,
        input_data=request.input_data,
        response=result.response,
    )
    if result.response.exit != 0 and not record_on_error:
        # A failed call is not cached by default: return the real failed response
        # so the caller sees exactly what happened, but store nothing, so the next
        # identical call runs fresh instead of replaying the failure. In REFRESH
        # this also means any existing (successful) cassette is left untouched.
        return Outcome(
            result.response, hit=False, recorded=False, cassette=cassette, failed_unstored=True
        )
    store.save(cassette)
    return Outcome(result.response, hit=False, recorded=True, cassette=cassette)


def apply_response(response: Response, output_dir: Path) -> None:
    """Write captured files into ``output_dir``, mirroring a real client.

    Paths are stored POSIX-style and are joined relative to ``output_dir``; any
    attempt to escape it (``..`` / absolute) is refused.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir.resolve()
    for f in response.files:
        target = (output_dir / Path(f.path)).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"refusing to write outside output dir: {f.path!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.to_bytes())
