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
    """The kind of document an Artifact holds.

    The ``STDOUT``/``STDERR``/``OUTPUT_FILE`` types are an execution's *output*,
    stored whenever caching is on. The ``INPUT_*`` types are the *input* sent to
    the client — and are stored only at ``DATASET`` persistence depth, to build a
    queryable ``(input, output)`` corpus. Each execution kind keeps its own input
    shape: managed-local uses ``INPUT_CONTEXT``/``INPUT_PROMPT``/``INPUT_SYSTEM``,
    the API kind a single ``INPUT_MESSAGES`` (the JSON message list), and
    passthrough a single ``INPUT_ARGS`` (the JSON native-argument list).

    RAW_USAGE is reserved for a later step (the raw client usage block stored as
    its own artifact); today raw usage still rides on TokenUsage.
    """

    STDOUT = "stdout"
    STDERR = "stderr"
    OUTPUT_FILE = "output_file"
    INPUT_CONTEXT = "input_context"
    INPUT_PROMPT = "input_prompt"
    INPUT_SYSTEM = "input_system"
    INPUT_MESSAGES = "input_messages"
    INPUT_ARGS = "input_args"


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


#: The artifact types that make up an execution's persisted *input* (DATASET
#: depth). A single place so consumers can tell input apart from output without
#: re-listing the members.
INPUT_ARTIFACT_TYPES = frozenset(
    {
        ArtifactType.INPUT_CONTEXT,
        ArtifactType.INPUT_PROMPT,
        ArtifactType.INPUT_SYSTEM,
        ArtifactType.INPUT_MESSAGES,
        ArtifactType.INPUT_ARGS,
    }
)
