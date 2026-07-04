# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemExecutionKeyLock: a per-key record-once lock spanning threads + processes.

Composes both levels of the record-once guarantee behind one ``acquire`` (X7): a
per-key in-process stripe lock (thread-level, the W29 pool) AND a per-key OS file lock
on ``<store>/locks/<key>.lock`` (process-level). The OS lock uses the same
``fcntl.flock`` (Unix/macOS) / ``msvcrt.locking`` (Windows) machinery as
``FilesystemStoreLock`` — cross-platform, no new dependency — and is released by the
OS when the holding process dies, so there is never a stale lock file.

Unlike the store lock (fail-fast, ``LOCK_NB``), this one BLOCKS with a bounded timeout:
it retries the non-blocking acquire until a deadline (portable to Windows, which has no
timed blocking flock), and on timeout PROCEEDS without the cross-process lock rather
than failing the user's call because a peer hung.

The wait is SIZED to the client call it protects (Y2): a contender waits out a peer's
whole client run (the client timeout + a margin) so an ordinary *slow* call coalesces
into one client run, and only a genuinely hung/dead peer — already past its own timeout
— ever falls through to a duplicate run. Composition passes that size to the constructor
via :func:`lock_wait_for_client_timeout`; the bare ``_DEFAULT_TIMEOUT_SECONDS`` is only a
fallback for a caller that does not size it. The never-block-the-user guarantee is kept:
an unbounded (``None``) client timeout still falls back to a bounded ceiling.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.execution_key_lock_port import (
    ExecutionKeyLockPort,
)

_LOCKS_DIRNAME = "locks"
#: A fixed pool of in-process stripes (W29): bounded memory, no per-key growth. The
#: stripes are RE-ENTRANT (RLock) so a thread holding one key's lock may acquire
#: another's even on a colliding stripe — eviction acquires victim keys' locks from
#: inside a record that already holds the recorded key's lock (X10).
_STRIPE_COUNT = 64
#: Fallback ceiling on the cross-process wait for a caller that does not size the wait
#: to a client call; on timeout the caller proceeds (possible duplicate WORK, never
#: duplicate corruption). Composition normally overrides this via the constructor.
_DEFAULT_TIMEOUT_SECONDS = 5.0
#: Poll interval while waiting for the OS lock — a non-blocking retry loop (portable).
_RETRY_INTERVAL_SECONDS = 0.05
#: Added to the client timeout when sizing the wait (Y2), so a peer that runs right up
#: to its timeout is still waited out rather than raced.
_LOCK_WAIT_MARGIN_SECONDS = 30.0
#: Bounded wait when the client timeout is unbounded (``None``): long enough to coalesce
#: a realistic call, short enough that a truly hung peer still eventually falls through,
#: honouring "never block the user forever" (X7).
_UNBOUNDED_CLIENT_WAIT_CEILING_SECONDS = 300.0


def lock_wait_for_client_timeout(client_timeout: float | None) -> float:
    """Size the per-key cross-process wait to the client call it protects (Y2).

    A contender should wait out a peer's whole client run — ``client_timeout`` plus a
    margin — so an ordinary slow call yields ONE client run (the winner's result is
    served to the waiter), and only a genuinely hung/dead peer past its own timeout ever
    falls through to a duplicate run. An unbounded (``None``) client timeout falls back
    to a bounded ceiling, keeping the never-block-the-user guarantee."""
    if client_timeout is None:
        return _UNBOUNDED_CLIENT_WAIT_CEILING_SECONDS
    return client_timeout + _LOCK_WAIT_MARGIN_SECONDS


def _try_lock(fd: int) -> bool:
    """Attempt the OS lock without blocking; return whether it was acquired."""
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class FilesystemExecutionKeyLock(ExecutionKeyLockPort):
    """Per-key record-once lock over ``<store>/locks/<key>.lock`` + an in-process stripe."""

    def __init__(
        self,
        store_root: Path,
        diag: DiagnosticsPort | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._locks_dir = Path(store_root) / _LOCKS_DIRNAME
        self._diag = diag
        self._timeout_seconds = timeout_seconds
        self._stripes = tuple(threading.RLock() for _ in range(_STRIPE_COUNT))
        # Keys this thread already holds the OS lock for, so a nested same-key acquire
        # is a no-op instead of self-denying: flock treats a second fd on the same file
        # as a separate holder even within one process, so re-opening + re-locking the
        # same key would spin the whole timeout out. The in-process stripe is already
        # re-entrant (RLock); this makes the process-level half re-entrant to match, so
        # the hit-time input back-fill (Y3) can take the key lock even when it runs
        # inside the miss path that already holds it (the coalescing re-check).
        self._held_by_thread = threading.local()

    def _held_keys(self) -> set[str]:
        keys: set[str] | None = getattr(self._held_by_thread, "keys", None)
        if keys is None:
            keys = set()
            self._held_by_thread.keys = keys
        return keys

    @contextmanager
    def acquire(self, execution_key: str) -> Generator[None]:
        # Thread-level first (fast, in-process), then process-level (the OS file lock).
        with self._stripes[hash(execution_key) % _STRIPE_COUNT]:
            held = self._held_keys()
            if execution_key in held:
                # Re-entrant same-key acquire on this thread: the OS lock is already held
                # by an outer acquire — nest as a no-op (see __init__).
                yield
                return
            fd = self._open_lock_file(execution_key)
            acquired = self._acquire_os_lock(fd, execution_key) if fd is not None else False
            held.add(execution_key)
            try:
                yield
            finally:
                held.discard(execution_key)
                if fd is not None:
                    if acquired:
                        _unlock(fd)
                    os.close(fd)

    def _lock_path(self, execution_key: str) -> Path:
        # Hash the key to a fixed-length, filesystem-safe name — an execution key is
        # already a fingerprint, but hashing bounds the length and forecloses any
        # path-unsafe character regardless of how a key is built.
        digest = hashlib.sha256(execution_key.encode("utf-8")).hexdigest()
        return self._locks_dir / f"{digest}.lock"

    def _open_lock_file(self, execution_key: str) -> int | None:
        """Open (creating) the key's lock file, or return None if the filesystem
        denies it — the lock then degrades to the in-process stripe only rather than
        failing the user's call (the port never raises to fail a call)."""
        try:
            self._locks_dir.mkdir(parents=True, exist_ok=True)
            return os.open(str(self._lock_path(execution_key)), os.O_CREAT | os.O_WRONLY)
        except OSError as exc:
            if self._diag:
                self._diag.warn(
                    "could not open the execution-key lock file — proceeding in-process only",
                    key=execution_key,
                    exc=exc,
                )
            return None

    def _acquire_os_lock(self, fd: int, execution_key: str) -> bool:
        """Block (bounded) for the cross-process lock via a non-blocking retry loop.
        Returns True if acquired; on timeout logs and returns False so the caller
        proceeds — degrading to possible duplicate work, never a blocked user."""
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            if _try_lock(fd):
                return True
            if time.monotonic() >= deadline:
                if self._diag:
                    self._diag.warn(
                        "execution-key lock timed out — proceeding without cross-process "
                        "exclusion (a peer may run the same key)",
                        key=execution_key,
                    )
                return False
            time.sleep(_RETRY_INTERVAL_SECONDS)
