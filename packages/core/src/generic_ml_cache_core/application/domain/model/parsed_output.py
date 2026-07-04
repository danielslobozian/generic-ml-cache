"""ParsedOutput."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.usage.usage import Usage


@dataclass(frozen=True)
class ParsedOutput:
    """What an adapter extracted from a client's structured output.

    ``text`` is the clean answer the caller should see on stdout (the client's
    own answer text, lifted out of its JSON wrapper). ``usage`` is the normalized
    envelope read from the same output, or ``None`` when the client offered no
    usage (or its output could not be parsed -- the text then falls back to the
    raw stdout so the core call still resolves).
    """

    text: str
    usage: Usage | None = None
