# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for BlobStorePort contract."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort


class InMemoryBlobStore(BlobStorePort):
    """Minimal in-memory implementation used to verify the port contract."""

    def __init__(self) -> None:
        self._store: dict = {}

    def get(self, key: str):
        return self._store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self._store[key] = output

    def remove(self, key: str) -> None:
        self._store.pop(key, None)


def test_get_returns_none_for_unknown_key():
    blob_store = InMemoryBlobStore()
    assert blob_store.get("unknown") is None


def test_put_then_get_returns_stored_bytes():
    blob_store = InMemoryBlobStore()
    blob_store.put("key1", b"hello world")
    assert blob_store.get("key1") == b"hello world"


def test_put_overwrites_existing_value():
    blob_store = InMemoryBlobStore()
    blob_store.put("key1", b"first")
    blob_store.put("key1", b"second")
    assert blob_store.get("key1") == b"second"


def test_different_keys_are_independent():
    blob_store = InMemoryBlobStore()
    blob_store.put("key1", b"value1")
    blob_store.put("key2", b"value2")
    assert blob_store.get("key1") == b"value1"
    assert blob_store.get("key2") == b"value2"


def test_remove_deletes_stored_bytes():
    blob_store = InMemoryBlobStore()
    blob_store.put("key1", b"value")
    blob_store.remove("key1")
    assert blob_store.get("key1") is None


def test_remove_is_a_no_op_for_unknown_key():
    blob_store = InMemoryBlobStore()
    blob_store.remove("never-stored")  # must not raise
    assert blob_store.get("never-stored") is None


def test_remove_leaves_other_keys_intact():
    blob_store = InMemoryBlobStore()
    blob_store.put("key1", b"one")
    blob_store.put("key2", b"two")
    blob_store.remove("key1")
    assert blob_store.get("key1") is None
    assert blob_store.get("key2") == b"two"


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BlobStorePort()  # type: ignore[abstract]


def test_port_requires_get_implementation():
    class MissingGet(BlobStorePort):
        def put(self, key: str, output: bytes) -> None:
            pass

        def remove(self, key: str) -> None:
            pass

    with pytest.raises(TypeError):
        MissingGet()  # type: ignore[abstract]


def test_port_requires_put_implementation():
    class MissingPut(BlobStorePort):
        def get(self, key: str):
            return None

        def remove(self, key: str) -> None:
            pass

    with pytest.raises(TypeError):
        MissingPut()  # type: ignore[abstract]


def test_port_requires_remove_implementation():
    class MissingRemove(BlobStorePort):
        def get(self, key: str):
            return None

        def put(self, key: str, output: bytes) -> None:
            pass

    with pytest.raises(TypeError):
        MissingRemove()  # type: ignore[abstract]
