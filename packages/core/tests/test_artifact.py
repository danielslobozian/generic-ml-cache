# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for Artifact and ArtifactType."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType


def test_artifact_type_values():
    assert ArtifactType.STDOUT.value == "stdout"
    assert ArtifactType.STDERR.value == "stderr"
    assert ArtifactType.OUTPUT_FILE.value == "output_file"


def test_artifact_type_string_roundtrip():
    for artifact_type in ArtifactType:
        assert ArtifactType(artifact_type.value) is artifact_type


def test_dehydrated_artifact_has_no_content():
    artifact = Artifact(artifact_type=ArtifactType.STDOUT, blob_key="abc123", size_bytes=10)
    assert artifact.content is None
    assert artifact.is_hydrated is False
    assert artifact.blob_key == "abc123"


def test_hydrated_artifact_carries_content():
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="abc123",
        size_bytes=5,
        content=b"hello",
    )
    assert artifact.is_hydrated is True
    assert artifact.content == b"hello"


def test_output_file_carries_a_name():
    artifact = Artifact(
        artifact_type=ArtifactType.OUTPUT_FILE,
        blob_key="def456",
        size_bytes=4,
        name="out/result.txt",
        content=b"done",
    )
    assert artifact.name == "out/result.txt"


def test_stream_artifacts_have_no_name_by_default():
    artifact = Artifact(artifact_type=ArtifactType.STDERR, blob_key="k", size_bytes=0)
    assert artifact.name is None


def test_default_encoding_is_utf8():
    artifact = Artifact(artifact_type=ArtifactType.STDOUT, blob_key="k", size_bytes=0)
    assert artifact.encoding == "utf-8"


def test_is_frozen():
    artifact = Artifact(artifact_type=ArtifactType.STDOUT, blob_key="k", size_bytes=0)
    with pytest.raises(FrozenInstanceError):
        artifact.blob_key = "other"  # type: ignore[misc]


# --- from_content factory ----------------------------------------------------


def test_from_content_derives_size_and_utf8_encoding():
    artifact = Artifact.from_content(ArtifactType.STDOUT, "key", b"hello")
    assert artifact.size_bytes == 5
    assert artifact.encoding == "utf-8"
    assert artifact.content == b"hello"
    assert artifact.blob_key == "key"


def test_from_content_detects_binary_content():
    artifact = Artifact.from_content(
        ArtifactType.OUTPUT_FILE, "key", b"\xff\xfe\x00", name="blob.bin"
    )
    assert artifact.encoding == "binary"
    assert artifact.name == "blob.bin"


def test_from_content_default_name_is_none():
    artifact = Artifact.from_content(ArtifactType.STDERR, "key", b"")
    assert artifact.name is None
    assert artifact.size_bytes == 0
    assert artifact.is_hydrated is True
