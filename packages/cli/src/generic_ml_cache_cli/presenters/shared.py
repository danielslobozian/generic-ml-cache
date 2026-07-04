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
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_use_case import (
    ReadArtifactBlobUseCase,
)

from generic_ml_cache_cli import __version__

# ---------------------------------------------------------------------------
# ANSI palette (256-colour)
# ---------------------------------------------------------------------------

_RESET = "\x1b[0m"
BOLD = "\x1b[1m"
TEAL = "\x1b[38;5;37m"  # accent / box rule
_TEAL_BRIGHT = "\x1b[38;5;43m"  # version
GREEN = "\x1b[38;5;42m"  # a hit
AMBER = "\x1b[38;5;214m"  # a miss
GREY = "\x1b[38;5;245m"  # secondary / dim

_TOKEN_BLOCKS = " ▏▎▍▌▋▊▉█"


def use_color() -> bool:
    """Colour only when writing to a real terminal and NO_COLOR is unset, so piped
    or redirected output never carries escape codes (the conventional contract)."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(text: str, *codes: str) -> str:
    """Wrap ``text`` in ANSI codes when colour is enabled (a real TTY with NO_COLOR
    unset), else return it unchanged -- so piped output never carries escape codes.
    Only gmlcache's own UI is ever painted; a client's answer is printed verbatim."""
    if not codes or not use_color():
        return text
    return "".join(codes) + text + _RESET


def format_bytes(byte_count: int) -> str:
    """Human-readable byte count using 1024-based units."""
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if byte_count >= threshold:
            return f"{byte_count / threshold:.1f} {unit}"
    return f"{byte_count} B"


def activity_bar(value: int, scale_maximum: int, width: int = 10) -> str:
    if scale_maximum <= 0:
        return " " * width
    filled = value / scale_maximum * width
    full = int(filled)
    bar = "█" * full + (_TOKEN_BLOCKS[int((filled - full) * 8)] if full < width else "")
    return (bar + " " * width)[:width]


def comma(count: int) -> str:
    return f"{count:,}"


def _token_str(count: int | None) -> str:
    """A token count for display: the number, or ``?`` when unknown (None)."""
    return "?" if count is None else str(count)


def usage_summary(usage: TokenUsage) -> str:
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
        rule, name, vers, sub, off = TEAL, BOLD, _TEAL_BRIGHT, GREY, _RESET
        bar_colors = [GREEN, GREY, GREY, GREY]
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
    rows: list[str] = []
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


def artifact_text(execution: MlExecution, artifact_type: ArtifactType) -> str:
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            return (artifact.content or b"").decode("utf-8", errors="replace")
    return ""


def stored_artifact_text(
    execution: MlExecution,
    artifacts: ReadArtifactBlobUseCase,
    artifact_type: ArtifactType,
) -> str:
    """Like ``artifact_text``, but hydrates the bytes via the artifact-content
    port when a stored execution carries only artifact metadata (``content is None``)."""
    from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
        ReadArtifactBlobCommand,
    )

    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            content = artifact.content
            if content is None:
                content = artifacts.read_blob(ReadArtifactBlobCommand(artifact.blob_key))
            return (content or b"").decode("utf-8", errors="replace")
    return ""


def run_exit_code(execution: MlExecution) -> int:
    if execution.failure is not None and execution.failure.exit_code is not None:
        return execution.failure.exit_code
    return 0 if execution.execution_state is ExecutionState.SUCCESS else 1


def apply_output_files(execution: MlExecution, output_dir: Path) -> None:
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
