# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemStoreLock.

These exercise the deterministic, in-process contract (acquire / contend / release)
on every platform. The auto-release-on-process-death property is the OS's guarantee
and is intentionally not tested by killing processes on CI.
"""

from __future__ import annotations

import pytest

from generic_ml_cache_core.adapter.out.persistence.filesystem_store_lock import FilesystemStoreLock
from generic_ml_cache_core.common.errors import StoreLocked


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
