# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for InProcessExecutionKeyLock — the thread-level record-once lock."""

from __future__ import annotations

import threading
import time

from generic_ml_cache_core.testing.in_process_execution_key_lock import (
    InProcessExecutionKeyLock,
)


def test_same_key_never_has_two_concurrent_holders():
    lock = InProcessExecutionKeyLock()
    guard = threading.Lock()
    current = 0
    max_concurrent = 0

    def worker() -> None:
        nonlocal current, max_concurrent
        with lock.acquire("same-key"):
            with guard:
                current += 1
                max_concurrent = max(max_concurrent, current)
            time.sleep(0.01)
            with guard:
                current -= 1

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_concurrent == 1  # the same key is mutually exclusive across threads


def test_the_lock_is_reusable_after_release():
    lock = InProcessExecutionKeyLock()
    with lock.acquire("k"):
        pass
    with lock.acquire("k"):  # a released lock can be re-acquired
        pass


def test_a_thread_can_nest_acquisitions_without_deadlock():
    # X10: the stripes are re-entrant (RLock) — a thread already holding a key's lock
    # (recording it) can acquire another key's lock (evicting a victim) even when they
    # collide on a stripe. Same-key nesting is the deterministic proof of re-entrancy.
    lock = InProcessExecutionKeyLock()
    with lock.acquire("k"):
        with lock.acquire("k"):  # a plain Lock would deadlock here
            pass
