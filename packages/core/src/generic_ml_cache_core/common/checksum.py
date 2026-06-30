# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Container-independent checksumming of cache inputs.

The whole point of this module is one invariant:

    The same *text* must yield the same checksum regardless of how that text
    happened to be stored -- whether it lived in a standalone file on disk or
    inside a JSON string field.

We achieve that by hashing the *decoded* UTF-8 text of each field, never the
bytes of whatever container (file, JSON document) carried it. Newlines, tabs
and other whitespace are meaningful and are never stripped.

Each field is length-prefixed before hashing so that, e.g., ``{"context": "ab",
"prompt": "c"}`` can never collide with ``{"context": "a", "prompt": "bc"}``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

# Control characters used purely as internal framing while hashing. They never
# touch user data and never appear in the stored record on disk.
_FIELD_SEP = b"\x1f"  # unit separator
_RECORD_SEP = b"\x1e"  # record separator
# Separates ordered arguments before hashing; order is significant (CLI flags
# are positional), so the join preserves it.
_ARGUMENT_SEP = "\x00"


def text_checksum(text: str) -> str:
    """SHA-256 of a single decoded string's UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_content_fingerprint(data: bytes) -> str:
    """The one shared rule for fingerprinting a declared input file's content.

    SHA-256 of the raw bytes -- binary-safe, so any file type fingerprints the
    same way regardless of encoding. This is the single function every front
    door (CLI, daemon, library consumer) must call; it is imported directly,
    never reimplemented, so two front doors can never derive different keys for
    the same file and silently miss each other's cache.
    """
    return hashlib.sha256(data).hexdigest()


def fingerprint_arguments(arguments: Sequence[str]) -> str:
    """Fingerprint an ordered argument list into the key.

    The raw arguments may carry secrets, so only their digest is ever keyed or
    stored. Order is significant; the join with a control separator preserves it.
    """
    return text_checksum(_ARGUMENT_SEP.join(arguments))


def checksum_input_data(input_data: Mapping[str, str]) -> str:
    """Return the container-independent SHA-256 checksum of ``input_data``.

    ``input_data`` is the cache input mapping, e.g. ``{"context": ..., "prompt":
    ...}``. Keys are hashed in sorted order so the result does not depend on dict
    ordering. Values must be ``str`` -- the cache is deliberately *dumb*, so it is
    the caller's job to make the text deterministic.
    """
    digest = hashlib.sha256()
    for key in sorted(input_data):
        value = input_data[key]
        if not isinstance(value, str):
            raise TypeError(
                f"input_data[{key!r}] must be str (the cache hashes decoded text, "
                f"not bytes or objects); got {type(value).__name__}"
            )
        encoded = value.encode("utf-8")
        digest.update(key.encode("utf-8"))
        digest.update(_FIELD_SEP)
        digest.update(str(len(encoded)).encode("ascii"))
        digest.update(_FIELD_SEP)
        digest.update(encoded)
        digest.update(_RECORD_SEP)
    return digest.hexdigest()
