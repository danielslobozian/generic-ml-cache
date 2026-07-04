# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ArtifactContentService — the artifact-content capability (read stored blobs)."""

from __future__ import annotations

from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
    ReadArtifactBlobCommand,
)
from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_use_case import (
    ReadArtifactBlobUseCase,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort


class ArtifactContentService(ReadArtifactBlobUseCase):
    """Hydrate stored artifact bytes via the blob-store out-port."""

    def __init__(self, blob_store: BlobStorePort) -> None:
        self._blob_store = blob_store

    def read_blob(self, command: ReadArtifactBlobCommand) -> bytes | None:
        return self._blob_store.get(command.blob_key)
