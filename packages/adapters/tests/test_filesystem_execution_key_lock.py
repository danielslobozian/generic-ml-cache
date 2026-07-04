# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemExecutionKeyLock — the per-key record-once lock (threads + OS)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort

from generic_ml_cache_adapters.adapter.outbound.persistence.filesystem_execution_key_lock import (
    _LOCK_WAIT_MARGIN_SECONDS,
    _UNBOUNDED_CLIENT_WAIT_CEILING_SECONDS,
    FilesystemExecutionKeyLock,
    lock_wait_for_client_timeout,
)


def test_acquire_creates_the_locks_dir_and_is_reusable(tmp_path: Path):
    lock = FilesystemExecutionKeyLock(tmp_path)
    with lock.acquire("k"):
        assert (tmp_path / "locks").is_dir()
    with lock.acquire("k"):  # released cleanly on exit → re-acquirable
        pass


def test_same_instance_serializes_concurrent_threads(tmp_path: Path):
    lock = FilesystemExecutionKeyLock(tmp_path)
    guard = threading.Lock()
    current = 0
    max_concurrent = 0

    def worker() -> None:
        nonlocal current, max_concurrent
        with lock.acquire("same"):
            with guard:
                current += 1
                max_concurrent = max(max_concurrent, current)
            time.sleep(0.01)
            with guard:
                current -= 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_concurrent == 1


def test_bounded_timeout_proceeds_when_another_holder_has_the_os_lock(tmp_path: Path):
    # Two independent lock instances over one store dir stand in for two processes:
    # their in-process stripes are separate, so the second contends only on the OS
    # file lock. When the first holds it, the second waits the bounded timeout and
    # then PROCEEDS (never hangs, never raises) — possible duplicate work, not a
    # blocked user (X7).
    holder = FilesystemExecutionKeyLock(tmp_path)
    diag = MagicMock(spec=DiagnosticsPort)
    waiter = FilesystemExecutionKeyLock(tmp_path, diag=diag, timeout_seconds=0.2)
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with holder.acquire("k"):
            held.set()
            release.wait(2.0)

    holder_thread = threading.Thread(target=hold)
    holder_thread.start()
    try:
        assert held.wait(2.0)
        started = time.monotonic()
        with waiter.acquire("k"):  # must not hang on the peer's OS lock
            elapsed = time.monotonic() - started
    finally:
        release.set()
        holder_thread.join()

    assert 0.2 <= elapsed < 2.0  # waited the bounded timeout, then proceeded
    diag.warn.assert_called()  # the fallback was logged


def test_wait_is_sized_to_the_client_timeout_plus_a_margin():
    # Y2: a bounded client timeout sizes the wait to timeout + margin, so a contender
    # waits out a peer's whole client call rather than tripping the old fixed 5s.
    assert lock_wait_for_client_timeout(60.0) == 60.0 + _LOCK_WAIT_MARGIN_SECONDS
    assert lock_wait_for_client_timeout(0.5) == 0.5 + _LOCK_WAIT_MARGIN_SECONDS


def test_wait_falls_back_to_a_bounded_ceiling_for_an_unbounded_timeout():
    # An unbounded (None) client timeout must not mean an unbounded wait — it falls
    # back to a bounded ceiling so a hung peer never blocks the user forever (X7).
    assert lock_wait_for_client_timeout(None) == _UNBOUNDED_CLIENT_WAIT_CEILING_SECONDS
