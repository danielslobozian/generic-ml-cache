# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ReadArtifactBlobCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadArtifactBlobCommand:
    """Read the stored bytes for ``blob_key`` (None if absent)."""

    blob_key: str
