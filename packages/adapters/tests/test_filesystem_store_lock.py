# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemStoreLock.

These exercise the deterministic, in-process contract (acquire / contend / release)
on every platform. The auto-release-on-process-death property is the OS's guarantee
and is intentionally not tested by killing processes on CI.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest
from generic_ml_cache_core.common.errors import StoreLocked

from generic_ml_cache_adapters.adapter.outbound.persistence.filesystem_store_lock import (
    FilesystemStoreLock,
)

#: The shared (read) lock is an fcntl capability; msvcrt has no advisory shared mode,
#: so the readers-writer semantics below are exercised on Unix/macOS only.
_UNIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="shared advisory locking is fcntl-only (no msvcrt LOCK_SH)"
)


def test_acquire_and_release(tmp_path):
    lock = FilesystemStoreLock(tmp_path)
    with lock.acquire():
        pass  # held here
    # released → can take it again
    with lock.acquire():
        pass


def test_second_holder_fails_fast_while_held(tmp_path):
    held = FilesystemStoreLock(tmp_path)
    other = FilesystemStoreLock(tmp_path)
    with held.acquire():
        with pytest.raises(StoreLocked):
            with other.acquire():
                pass


def test_lock_is_released_after_the_block(tmp_path):
    first = FilesystemStoreLock(tmp_path)
    second = FilesystemStoreLock(tmp_path)
    with first.acquire():
        pass
    # first released on exit, so a different instance can now acquire
    with second.acquire():
        pass


def test_release_happens_even_on_exception(tmp_path):
    lock = FilesystemStoreLock(tmp_path)
    with pytest.raises(ValueError):
        with lock.acquire():
            raise ValueError("boom")
    # the lock must have been released despite the exception
    with FilesystemStoreLock(tmp_path).acquire():
        pass


# --- X8: readers-writer (shared content writes vs exclusive migration) --------


@_UNIX_ONLY
def test_two_shared_holders_coexist(tmp_path):
    # Concurrent content writes both take the lock shared and run together.
    writer_a = FilesystemStoreLock(tmp_path)
    writer_b = FilesystemStoreLock(tmp_path)
    with writer_a.acquire_shared():
        with writer_b.acquire_shared():  # a second shared holder is allowed
            pass


@_UNIX_ONLY
def test_exclusive_fails_fast_while_a_shared_lock_is_held(tmp_path):
    # A migration cannot start over an in-flight content write — it fails fast, so no
    # blob is transformed while a plaintext write is mid-flight.
    writer = FilesystemStoreLock(tmp_path)
    migration = FilesystemStoreLock(tmp_path)
    with writer.acquire_shared():
        with pytest.raises(StoreLocked):
            with migration.acquire():
                pass


@_UNIX_ONLY
def test_shared_blocks_until_an_exclusive_holder_releases(tmp_path):
    # Once a migration holds the exclusive lock, a NEW content write's shared acquire
    # waits it out rather than slipping a plaintext blob into the half-encrypted store.
    migration = FilesystemStoreLock(tmp_path)
    writer = FilesystemStoreLock(tmp_path)
    holding = threading.Event()

    def hold_exclusive_briefly() -> None:
        with migration.acquire():
            holding.set()
            time.sleep(0.2)

    thread = threading.Thread(target=hold_exclusive_briefly)
    thread.start()
    try:
        assert holding.wait(2.0)
        started = time.monotonic()
        with writer.acquire_shared():  # blocks until the migration's hold ends
            elapsed = time.monotonic() - started
    finally:
        thread.join()

    assert elapsed >= 0.15  # waited the exclusive holder out
