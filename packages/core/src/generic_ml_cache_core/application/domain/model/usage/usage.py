# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The usage envelope: what one recorded call consumed, in a common shape.

Two things live here:

* :class:`Usage` -- a **normalized** token/cost envelope with a small core every
  client fills, plus an optional ring only some report. It keeps the client's
  **raw** usage block verbatim alongside, so nothing the client reported is lost.
* :class:`ParsedOutput` -- what an adapter pulls out of a client's structured
  output: the clean answer text (what the caller sees on stdout) and the
  :class:`Usage` it read from the same output.

Design rulings this encodes (do not relitigate):

* **Tokens are the spine, not dollars.** Every client reports tokens; only some
  report a dollar figure, and even that figure is the *client's own local
  estimate* (computed from a price table bundled into the client at build time),
  not authoritative billing. So ``cost_usd`` is advisory: recorded when offered,
  never derived by the cache, never authoritative.
* **Unknown is not zero.** A field the client did not report is ``None``
  ("unknown"), never ``0``. Codex reports no cache-write count -- that is unknown,
  not "wrote nothing". This distinction is in the type from the start because we
  cannot anticipate what any given client (or client version, or detached/parallel
  run) chooses to report.
* **We record what the call reported; we do not reconstruct.** If a client
  under-reports (e.g. subagents that billed outside the single invocation we
  launched), that is the client's gap; we mark it unknown rather than invent a
  total.
* **The model the call ran under lives on the stored execution** (its ``model`` field), so
  a reader always shows usage *next to its model* -- a Haiku token is not an Opus
  token. The full per-model / per-subagent breakdown a client may give (e.g.
  Claude's ``modelUsage``) is preserved in :attr:`Usage.raw`, not flattened here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from generic_ml_cache_core.common.immutable import deep_freeze, thaw


def int_or_none(value: Any) -> int | None:
    """Coerce a client-reported count to ``int``, or ``None`` if absent/unusable.

    Used by adapters reading a client's JSON: a missing or non-numeric field
    becomes ``None`` ("unknown"), never ``0``, so a value the client did not
    report is never mistaken for a real zero.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def float_or_none(value: Any) -> float | None:
    """Coerce a client-reported amount to ``float``, or ``None`` if absent/unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Usage:
    """Normalized token counts for one recorded call, with the raw block kept.

    The parse-at-edge shape: it is built by normalizing a client's reported usage
    block as its output is parsed (``parsed_output`` + the claude/codex/cursor
    adapters). Its stored counterpart is :class:`TokenUsage` — the same counts as a
    database-bound domain type. Two legitimate layers (parse-at-edge → stored
    domain), not a duplication.

    Every count is ``Optional[int]``: a value the client reported, or ``None``
    when it did not report that count at all. ``cost_usd`` is the client's own
    estimate in US dollars when it offered one (advisory only -- see module docs),
    else ``None``. ``raw`` is the client's verbatim usage structure, so a caller
    that wants a client-specific field we did not normalize can read it straight
    from the stored execution.
    """

    #: Prompt/input tokens the call consumed.
    input_tokens: int | None = None
    #: Generated/output tokens. For clients that fold reasoning into output
    #: (Claude), reasoning is included here and ``reasoning_tokens`` is unknown.
    output_tokens: int | None = None
    #: Input tokens served from the client's prompt cache (a reduced-rate read).
    cache_read_tokens: int | None = None
    #: Input tokens spent writing new prompt-cache entries. Unknown for clients
    #: that do not report a cache-write count (e.g. Codex).
    cache_write_tokens: int | None = None
    #: Reasoning tokens reported *separately* from output (e.g. Codex). Unknown
    #: when the client folds reasoning into output (Claude) or omits it (Cursor).
    reasoning_tokens: int | None = None
    #: The client's own dollar estimate for the call, when it reports one (only
    #: Claude does, today). Advisory, not authoritative billing; never derived.
    cost_usd: float | None = None
    #: The client's verbatim usage structure (lossless), so unanticipated
    #: client-specific fields stay reachable. Shape is per-client.
    raw: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", deep_freeze(self.raw))

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": self.cost_usd,
            "raw": thaw(self.raw),
        }
