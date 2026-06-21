# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Artifact and ArtifactType."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional

_UTF8 = "utf-8"
_BINARY = "binary"


class ArtifactType(enum.Enum):
    """The kind of generated output an Artifact holds.

    RAW_USAGE is reserved for a later step (the raw client usage block stored as
    its own artifact); today raw usage still rides on TokenUsage.
    """

    STDOUT = "stdout"
    STDERR = "stderr"
    OUTPUT_FILE = "output_file"


@dataclass(frozen=True)
class Artifact:
    """One generated document of an execution's output.

    An artifact is a STORED thing: it always has a ``blob_key`` (the content
    checksum addressing its bytes in the blob store). ``content`` is materialised
    only when the artifact is hydrated; dehydrated, only the reference remains.
    The use case — never the client runner — computes the key and stores the
    bytes; this object just records the result.
    """

    artifact_type: ArtifactType
    blob_key: str
    size_bytes: int
    name: Optional[str] = None
    encoding: str = _UTF8
    content: Optional[bytes] = None

    @classmethod
    def from_content(
        cls,
        artifact_type: ArtifactType,
        blob_key: str,
        content: bytes,
        name: Optional[str] = None,
    ) -> "Artifact":
        """Build a hydrated artifact from its bytes, deriving size and encoding.

        The caller has already computed ``blob_key`` and stored the bytes; this
        only assembles the value object from the content it owns.
        """
        return cls(
            artifact_type=artifact_type,
            blob_key=blob_key,
            size_bytes=len(content),
            name=name,
            encoding=cls._encoding_for(content),
            content=content,
        )

    @staticmethod
    def _encoding_for(content: bytes) -> str:
        try:
            content.decode(_UTF8)
            return _UTF8
        except UnicodeDecodeError:
            return _BINARY

    @property
    def is_hydrated(self) -> bool:
        """True when the artifact's bytes are materialised in memory."""
        return self.content is not None
