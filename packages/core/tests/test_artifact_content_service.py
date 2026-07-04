# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ArtifactContentService (the artifact-content inbound capability)."""

from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
    ReadArtifactBlobCommand,
)
from generic_ml_cache_core.application.usecase.artifact_content_service import (
    ArtifactContentService,
)


class _FakeBlobStore:
    def get(self, key):
        return b"hello" if key == "k1" else None


def test_read_blob_delegates():
    svc = ArtifactContentService(_FakeBlobStore())  # type: ignore[arg-type]
    assert svc.read_blob(ReadArtifactBlobCommand("k1")) == b"hello"
    assert svc.read_blob(ReadArtifactBlobCommand("absent")) is None
