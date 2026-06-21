# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for BlobStorePort contract."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.port.out.blob_store_port import BlobStorePort


class InMemoryBlobStore(BlobStorePort):
    """Minimal in-memory implementation used to verify the port contract."""

    def __init__(self) -> None:
        self._store: dict = {}

    def get(self, key: str):
        return self._store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self._store[key] = output


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


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BlobStorePort()  # type: ignore[abstract]


def test_port_requires_get_implementation():
    class MissingGet(BlobStorePort):
        def put(self, key: str, output: bytes) -> None:
            pass

    with pytest.raises(TypeError):
        MissingGet()  # type: ignore[abstract]


def test_port_requires_put_implementation():
    class MissingPut(BlobStorePort):
        def get(self, key: str):
            return None

    with pytest.raises(TypeError):
        MissingPut()  # type: ignore[abstract]
