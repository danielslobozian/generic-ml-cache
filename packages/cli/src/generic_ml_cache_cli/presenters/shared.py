# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared display helpers: ANSI palette, byte formatting, banner, and execution result helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution

from generic_ml_cache_cli import __version__

# ---------------------------------------------------------------------------
# ANSI palette (256-colour)
# ---------------------------------------------------------------------------

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_TEAL = "\x1b[38;5;37m"  # accent / box rule
_TEAL_BRIGHT = "\x1b[38;5;43m"  # version
_GREEN = "\x1b[38;5;42m"  # a hit
_AMBER = "\x1b[38;5;214m"  # a miss
_GREY = "\x1b[38;5;245m"  # secondary / dim

_TOKEN_BLOCKS = " ▏▎▍▌▋▊▉█"


def _use_color() -> bool:
    """Colour only when writing to a real terminal and NO_COLOR is unset, so piped
    or redirected output never carries escape codes (the conventional contract)."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _paint(text: str, *codes: str) -> str:
    """Wrap ``text`` in ANSI codes when colour is enabled (a real TTY with NO_COLOR
    unset), else return it unchanged -- so piped output never carries escape codes.
    Only gmlcache's own UI is ever painted; a client's answer is printed verbatim."""
    if not codes or not _use_color():
        return text
    return "".join(codes) + text + _RESET


def _format_bytes(n: int) -> str:
    """Human-readable byte count using 1024-based units."""
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def _activity_bar(value: int, maxval: int, width: int = 10) -> str:
    if maxval <= 0:
        return " " * width
    filled = value / maxval * width
    full = int(filled)
    bar = "█" * full + (_TOKEN_BLOCKS[int((filled - full) * 8)] if full < width else "")
    return (bar + " " * width)[:width]


def _comma(n: int) -> str:
    return f"{n:,}"


def _token_str(count: "int | None") -> str:
    """A token count for display: the number, or ``?`` when unknown (None)."""
    return "?" if count is None else str(count)


def _usage_summary(usage) -> str:
    """One-line token summary; unknown counts show as ``?`` (never 0)."""
    return (
        f"input={_token_str(usage.input_tokens)} "
        f"output={_token_str(usage.output_tokens)} "
        f"cache-read={_token_str(usage.cache_read_tokens)} "
        f"cache-write={_token_str(usage.cache_write_tokens)} "
        f"reasoning={_token_str(usage.reasoning_tokens)}"
    )


def render_banner(color: bool = False) -> str:
    """The boxed gmlcache banner: the cache mark (four hollow bars; the top one is
    the accent 'hit') beside the title, version, and tagline. Width is derived from
    the content so everything stays aligned. ``color`` adds ANSI; off yields plain."""
    title = "gmlcache"
    ver = __version__
    tag = "record · replay · check · sessions · encryption"

    # The mark: four hollow bars -- thin walls (▏ ▕) around a double-line body (═),
    # widths echoing the logo. The first bar is the accent ("hit"); the rest are dim.
    bars = ["▏" + "═" * n + "▕" for n in (11, 7, 10, 5)]
    bar_w = max(len(b) for b in bars)

    if color:
        rule, name, vers, sub, off = _TEAL, _BOLD, _TEAL_BRIGHT, _GREY, _RESET
        bar_colors = [_GREEN, _GREY, _GREY, _GREY]
    else:
        rule = name = vers = sub = off = ""
        bar_colors = ["", "", "", ""]

    left_pad, gap = "  ", "  "
    texts = ["", tag, "", ""]  # the tagline sits on the second bar row

    body_w = max(len(left_pad) + bar_w + len(gap) + len(t) for t in texts)
    left_top = f"─ {title} "
    right_top = f" {ver} ─"
    inner = max(len(left_top) + 6 + len(right_top), body_w + 1)
    top_dashes = inner - len(left_top) - len(right_top)

    top = (
        f"{rule}┌─ {off}{name}{title}{off}"
        f"{rule} {'─' * top_dashes} {off}{vers}{ver}{off}{rule} ─┐{off}"
    )
    rows = []
    for bar, bar_color, text in zip(bars, bar_colors, texts, strict=True):
        bar_cell = f"{bar_color}{bar}{off}" + " " * (bar_w - len(bar))
        used = len(left_pad) + bar_w + len(gap) + len(text)
        rows.append(
            f"{rule}│{off}{left_pad}{bar_cell}{gap}{sub}{text}{off}"
            f"{' ' * (inner - used)}{rule}│{off}"
        )
    bot = f"{rule}└{'─' * inner}┘{off}"
    return "\n".join([top, *rows, bot])


# ---------------------------------------------------------------------------
# Execution result helpers
# ---------------------------------------------------------------------------


def _artifact_text(execution: MlExecution, artifact_type: ArtifactType) -> str:
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            return (artifact.content or b"").decode("utf-8", errors="replace")
    return ""


def _stored_artifact_text(execution: MlExecution, blob_store, artifact_type: ArtifactType) -> str:
    """Like ``_artifact_text``, but hydrates the bytes from the blob store when a
    stored execution carries only artifact metadata (``content is None``)."""
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            content = artifact.content
            if content is None:
                content = blob_store.get(artifact.blob_key)
            return (content or b"").decode("utf-8", errors="replace")
    return ""


def _run_exit_code(execution: MlExecution) -> int:
    if execution.failure is not None and execution.failure.exit_code is not None:
        return execution.failure.exit_code
    return 0 if execution.execution_state is ExecutionState.SUCCESS else 1


def _apply_output_files(execution: MlExecution, output_dir: Path) -> None:
    """Write captured output files into ``output_dir``, mirroring a real client.
    Any attempt to escape the directory (``..`` / absolute) is refused."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir.resolve()
    for artifact in execution.artifacts:
        if artifact.artifact_type is not ArtifactType.OUTPUT_FILE or artifact.name is None:
            continue
        target = (output_dir / Path(artifact.name)).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"refusing to write outside output dir: {artifact.name!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content or b"")
