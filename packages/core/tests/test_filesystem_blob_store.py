# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemBlobStore."""

from __future__ import annotations

from generic_ml_cache_core.adapter.out.storage.filesystem_blob_store import FilesystemBlobStore
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort


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
