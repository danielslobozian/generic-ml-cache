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
    client: str
    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: Optional[str] = None
    # Declared input files the client will read *in place*: {absolute_path: content_sha256}.
    # Only the content fingerprint enters the key (folded into input_data below); the paths
    # are used solely to open the read-door at record time and are never part of the key.
    # Same content -> same key (rename-invariant); identical-content files collapse to one
    # entry; order is irrelevant (input_data is hashed by sorted key).
    input_files: Dict[str, str] = field(default_factory=dict)

    @property
    def input_data(self) -> Dict[str, str]:
        data = {"context": self.context, "prompt": self.prompt}
        for sha in self.input_files.values():
            data[f"input_file:{sha}"] = sha
        return data

    @property
    def allowed_read_paths(self) -> List[str]:
        """The declared file paths, sorted -- what the door is opened for."""
        return sorted(self.input_files)


@dataclass
class Outcome:
    """What the cache did and the response it resolved to."""

    response: Response
    hit: bool  # True if served from an existing cassette
    recorded: bool  # True if a real call was made and stored
    cassette: Cassette


def resolve(
    request: Request,
    store: CassetteStore,
    mode: Mode = Mode.CACHE,
    executable: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Outcome:
    """Resolve a request against the store under ``mode`` (no I/O to caller)."""
    adapter = get_adapter(request.client)

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
