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

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .adapters.registry import get_adapter
from .cassette import Cassette, Response
from .errors import CacheMiss
from .isolation import record_real_call
from .store import CassetteStore


class Mode(enum.Enum):
    OFFLINE = "offline"
    CACHE = "cache"
    REFRESH = "refresh"


@dataclass
class Request:
    """A single cache request -- the full identity of one client call.

    Fields:
        client: registered client name (e.g. ``claude``, ``codex``, ``cursor``).
        model:  the model id, passed through to the client verbatim.
        effort: reasoning-effort level; an empty string means "unset" (the client
            applies its own default). A distinct value in the key.
        context: optional supporting material, merged ahead of the prompt when the
            client is invoked. Part of the key.
        prompt: the task instruction (required for a run). Part of the key.
        user_system_prompt: an optional caller-supplied system prompt, layered
            after the cache's prime directive at record time. NOT part of the key.
        input_files: declared files the client will read *in place*, as
            ``{absolute_path: content_sha256}``. Only the content fingerprint
            enters the key (folded into ``input_data``); the paths serve solely to
            open the read-door at record time and are never keyed. Same content ->
            same key (rename-invariant), identical contents collapse to one entry,
            and order is irrelevant.
        allow_paths: declared folders the client may *scan* (read) whose contents
            are unbounded and cannot be fingerprinted (absolute paths). Their mere
            presence makes the call **non-cacheable** -- it runs fresh and stores
            nothing (passthrough) -- unless scan-trust is explicitly enabled. Never
            keyed; they only open the read-door (directive + a client's hard read
            flag where available).

    The key is derived from ``client``, ``model``, ``effort`` and ``input_data``
    only -- i.e. context, prompt and the input-file fingerprints (see
    ``input_data``). The user system prompt, the prime directive and the
    allow-path folders are all record-time scaffolding and are deliberately
    excluded from the key.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: Optional[str] = None
    input_files: Dict[str, str] = field(default_factory=dict)
    allow_paths: List[str] = field(default_factory=list)

    @property
    def input_data(self) -> Dict[str, str]:
        data = {"context": self.context, "prompt": self.prompt}
        for sha in self.input_files.values():
            data[f"input_file:{sha}"] = sha
        return data

    @property
    def allowed_read_paths(self) -> List[str]:
        """All paths the read-door is opened for: input files + allow-path folders."""
        return sorted([*self.input_files, *self.allow_paths])

    @property
    def add_dir_paths(self) -> List[str]:
        """Allow-path folders, sorted -- granted via a client's hard read flag
        (e.g. Claude's ``--add-dir``) where one exists."""
        return sorted(self.allow_paths)

    @property
    def requires_passthrough(self) -> bool:
        """True when the call declares unfingerprintable folders -> not cacheable."""
        return bool(self.allow_paths)


@dataclass
class Outcome:
    """What the cache did and the response it resolved to."""

    response: Response
    hit: bool  # True if served from an existing cassette
    recorded: bool  # True if a real call was made and stored
    cassette: Cassette
    passthrough: bool = False  # True if it ran fresh and stored nothing (allow-path)


def resolve(
    request: Request,
    store: CassetteStore,
    mode: Mode = Mode.CACHE,
    executable: Optional[str] = None,
    timeout: Optional[float] = None,
    trust_scan: bool = False,
) -> Outcome:
    """Resolve a request against the store under ``mode`` (no I/O to caller).

    A call that declares ``allow_paths`` reads folders the cache cannot
    fingerprint, so by default it is **passthrough**: it always runs fresh and
    stores nothing (no hit is ever served for it). ``trust_scan`` is the explicit,
    opt-in override that lets such a call be cached anyway (the caller asserts the
    folders are stable); it is wired here but not yet exposed.
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
            from .checksum import checksum_input_data

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
    )
    cassette = Cassette(
        client=request.client,
        model=request.model,
        effort=request.effort,
        input_data=request.input_data,
        response=result.response,
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
