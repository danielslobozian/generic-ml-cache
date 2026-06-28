# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FileFingerprintPort contract and its filesystem adapter."""

from __future__ import annotations

import hashlib

import pytest

from generic_ml_cache_adapters.adapter.out.fingerprint.filesystem_file_fingerprint import (
    FilesystemFileFingerprint,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.common.errors import InputFileError


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        FileFingerprintPort()  # type: ignore[abstract]


def test_port_requires_fingerprint_implementation():
    class MissingFingerprint(FileFingerprintPort):
        pass

    with pytest.raises(TypeError):
        MissingFingerprint()  # type: ignore[abstract]


def test_filesystem_adapter_is_a_file_fingerprint_port():
    assert isinstance(FilesystemFileFingerprint(), FileFingerprintPort)


def test_fingerprint_is_sha256_of_file_bytes(tmp_path):
    sample = b"file content\nsecond line\n"
    input_file = tmp_path / "input.txt"
    input_file.write_bytes(sample)

    fingerprint = FilesystemFileFingerprint().fingerprint(str(input_file))
    assert fingerprint == hashlib.sha256(sample).hexdigest()


def test_fingerprint_is_deterministic_across_paths_with_same_content(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"identical")
    (tmp_path / "b.txt").write_bytes(b"identical")
    adapter = FilesystemFileFingerprint()
    assert adapter.fingerprint(str(tmp_path / "a.txt")) == adapter.fingerprint(
        str(tmp_path / "b.txt")
    )


def test_fingerprint_handles_binary_content(tmp_path):
    binary = b"\xff\xfe\x00\x01\x02"
    binary_file = tmp_path / "blob.bin"
    binary_file.write_bytes(binary)
    fingerprint = FilesystemFileFingerprint().fingerprint(str(binary_file))
    assert fingerprint == hashlib.sha256(binary).hexdigest()


def test_missing_file_raises_input_file_error(tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(InputFileError):
        FilesystemFileFingerprint().fingerprint(str(missing))


def test_directory_path_raises_input_file_error(tmp_path):
    with pytest.raises(InputFileError):
        FilesystemFileFingerprint().fingerprint(str(tmp_path))


def test_unreadable_existing_file_raises_input_file_error(tmp_path, monkeypatch):
    """A file that exists but cannot be read (e.g. a permission error mid-read)
    translates the foreign OSError into InputFileError — not a silent skip."""
    from pathlib import Path

    input_file = tmp_path / "locked.txt"
    input_file.write_bytes(b"secret")

    def _deny_read(self):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", _deny_read)
    with pytest.raises(InputFileError):
        FilesystemFileFingerprint().fingerprint(str(input_file))
