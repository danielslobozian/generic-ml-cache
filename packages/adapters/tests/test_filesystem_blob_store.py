# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemBlobStore."""

from __future__ import annotations

import os
import threading

from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort

from generic_ml_cache_adapters.adapter.outbound.storage.filesystem_blob_store import (
    FilesystemBlobStore,
)


def test_is_a_blob_store_port(tmp_path):
    assert isinstance(FilesystemBlobStore(tmp_path), BlobStorePort)


def test_get_unknown_key_returns_none(tmp_path):
    assert FilesystemBlobStore(tmp_path).get("missing") is None


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


def test_exists_reflects_presence(tmp_path):
    blob_store = FilesystemBlobStore(tmp_path)
    assert blob_store.exists("key1") is False
    blob_store.put("key1", b"value")
    assert blob_store.exists("key1") is True
    blob_store.remove("key1")
    assert blob_store.exists("key1") is False


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
