# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemBlobStore."""

from __future__ import annotations

import os
import threading

import pytest
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.common.errors import CacheError, StoreUnavailable

from generic_ml_cache_adapters.adapter.outbound.storage.filesystem_blob_store import (
    FilesystemBlobStore,
)


def test_is_a_blob_store_port(tmp_path):
    assert isinstance(FilesystemBlobStore(tmp_path), BlobStorePort)


def test_every_blobkey_resolves_strictly_within_the_store_root(tmp_path):
    # The containment guarantee (W7/W23/X16): the store holds no BESPOKE traversal
    # check — it re-wraps the key through BlobKey and resolves root / key. So every
    # validly constructed key, whatever its shape, must land strictly under the root.
    blob_store = FilesystemBlobStore(tmp_path)
    root = tmp_path.resolve()
    for value in ("a", "a.b-c_d", "x" * 255, "deadbeef.req", "..req"):
        blob_store.put(BlobKey(value), b"data")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert root in path.resolve().parents


def test_a_raw_traversal_string_is_rejected_at_the_adapter_boundary(tmp_path):
    # X16: this is a PUBLIC installable adapter an embedder calls DIRECTLY with a raw
    # str, which Python lets masquerade as a BlobKey. The adapter re-wraps every key
    # through BlobKey, so a traversal string is rejected at get/put/remove — it never
    # resolves outside the root. (The prior test raised at BlobKey(bad) construction,
    # before put was even entered, so it never exercised this boundary.)
    blob_store = FilesystemBlobStore(tmp_path)
    outside = tmp_path.parent / "evil"
    for bad in ("../evil", "a/b", "/abs", "..", "."):
        with pytest.raises(ValueError, match="invalid blob key"):
            blob_store.put(bad, b"pwn")  # a raw str, NOT BlobKey(bad)
        with pytest.raises(ValueError, match="invalid blob key"):
            blob_store.get(bad)
        with pytest.raises(ValueError, match="invalid blob key"):
            blob_store.remove(bad)
    assert not outside.exists()  # nothing escaped the store root


def test_get_unknown_key_returns_none(tmp_path):
    assert FilesystemBlobStore(tmp_path).get("missing") is None


# ---------------------------------------------------------------------------
# IO-failure boundary translation (Y5): an existing-but-unreadable blob, or a
# failing write/remove, surfaces as a CacheError (StoreUnavailable), never a raw
# OSError. Absent stays None; a bad KEY stays the X16 ValueError guard.
# ---------------------------------------------------------------------------


def test_get_on_an_unreadable_blob_surfaces_store_unavailable(tmp_path):
    store = FilesystemBlobStore(tmp_path)
    # A directory sitting where a blob file is expected: exists() is True, but the
    # read raises IsADirectoryError (an OSError), which is translated at the boundary.
    (tmp_path / "blobkey").mkdir()
    with pytest.raises(StoreUnavailable) as excinfo:
        store.get("blobkey")
    assert isinstance(excinfo.value, CacheError)  # no raw OSError reaches a driver


def test_put_failure_surfaces_store_unavailable(tmp_path):
    store = FilesystemBlobStore(tmp_path)
    # A non-empty directory at the destination path: os.replace onto it raises OSError.
    (tmp_path / "blobkey").mkdir()
    (tmp_path / "blobkey" / "sentinel").write_text("x")
    with pytest.raises(StoreUnavailable):
        store.put("blobkey", b"data")


def test_remove_failure_surfaces_store_unavailable(tmp_path):
    store = FilesystemBlobStore(tmp_path)
    # unlink on a directory raises IsADirectoryError (missing_ok only masks absence).
    (tmp_path / "blobkey").mkdir()
    with pytest.raises(StoreUnavailable):
        store.remove("blobkey")


def test_put_then_get_round_trip(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    blob_store.put("key1", b"hello world")
    assert blob_store.get("key1") == b"hello world"


def test_put_handles_binary_content(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    blob_store.put("key1", b"\xff\xfe\x00\x01")
    assert blob_store.get("key1") == b"\xff\xfe\x00\x01"


def test_put_overwrites(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    blob_store.put("key1", b"first")
    blob_store.put("key1", b"second")
    assert blob_store.get("key1") == b"second"


def test_is_healthy_true_for_a_writable_root(tmp_path):
    assert FilesystemBlobStore(tmp_path).is_healthy() is True


def test_is_healthy_false_when_the_root_cannot_be_written(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    # The root sits under a file, so the health folder cannot be created — unhealthy.
    assert FilesystemBlobStore(blocker / "store").is_healthy() is False


def test_is_healthy_leaves_no_probe_files_behind(tmp_path):
    store = FilesystemBlobStore(tmp_path)
    store.is_healthy()
    health_dir = tmp_path / ".health"
    assert not any(health_dir.iterdir())  # the canary is removed after the probe


def test_remove_deletes(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    blob_store.put("key1", b"value")
    blob_store.remove("key1")
    assert blob_store.get("key1") is None


def test_remove_unknown_key_is_a_no_op(tmp_path):
    FilesystemBlobStore(tmp_path).remove("never-stored")  # must not raise


def test_blobs_persist_across_instances(tmp_path):
    FilesystemBlobStore(tmp_path).put("key1", b"durable")
    # A fresh instance on the same root sees the blob (cross-process persistence).
    assert FilesystemBlobStore(tmp_path).get("key1") == b"durable"


def test_leaves_no_temp_files_behind(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    blob_store.put("key1", b"value")
    assert [p.name for p in tmp_path.iterdir()] == ["key1"]


def test_each_write_mints_a_distinct_temp_file(tmp_path, monkeypatch):
    # Two writes to the SAME key must use two DIFFERENT scratch files, so a
    # concurrent second writer can never publish a first writer's half-written
    # temp. Record the source path handed to os.replace on each write.
    blob_store = FilesystemBlobStore(tmp_path)
    replaced_temp_names: list[str] = []
    real_replace = os.replace

    def recording_replace(source, destination):
        replaced_temp_names.append(str(source))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", recording_replace)
    blob_store.put("shared-key", b"first")
    blob_store.put("shared-key", b"second")

    assert len(set(replaced_temp_names)) == 2


def test_concurrent_writes_to_the_same_key_do_not_collide(tmp_path):
    # Content-addressing means two different executions that share a blob write
    # the SAME key with byte-identical content in parallel. A per-write temp lets
    # every writer land cleanly; the old per-process temp made them clobber one
    # scratch file (FileNotFoundError on os.replace, or a leftover temp).
    blob_store = FilesystemBlobStore(tmp_path)
    identical_content = b"x" * 200_000
    writer_count = 16
    start_barrier = threading.Barrier(writer_count)
    write_errors: list[BaseException] = []

    def write_shared_blob():
        start_barrier.wait()
        try:
            blob_store.put("shared-key", identical_content)
        except BaseException as write_error:
            write_errors.append(write_error)

    writers = [threading.Thread(target=write_shared_blob) for _ in range(writer_count)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    assert write_errors == []
    assert blob_store.get("shared-key") == identical_content
    assert [p.name for p in tmp_path.iterdir()] == ["shared-key"]
