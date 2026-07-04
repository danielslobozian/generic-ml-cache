# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ReadArtifactBlobUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
    ReadArtifactBlobCommand,
)


class ReadArtifactBlobUseCase(ABC):
    """Inbound port: the stored bytes for an artifact blob key, or None."""

    @abstractmethod
    def read_blob(self, command: ReadArtifactBlobCommand) -> bytes | None: ...
