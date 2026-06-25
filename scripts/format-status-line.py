#!/usr/bin/env python3
"""format-status-line.py — default gmlcache status-bar formatter.

Pulls from four data sources and assembles a single status line:

  1. git           — repo name, branch, HEAD hash, dirty-file count
  2. gmlcache      — session ID, tags, calls/hits, per-model token usage
  3. cwd           — abbreviated current working directory
  4. ctt            — Claude 5-hour rolling quota ("ctt prompt --no-cloud")

Each section is independent — if a source is unavailable (daemon not running,
not a git repo, ctt not installed) the section is silently omitted.

CUSTOMISE: comment out any section you don't need, rearrange the order in
main(), or change the icon/format variables at the top of each section.

Usage — wire into Claude Code's status bar via .claude/settings.json:
  {
    "statusLine": "python3 /path/to/scripts/format-status-line.py"
  }
"""

from __future__ import annotations

import json
import os
import subprocess

_SEP = "  │  "


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 2) -> str:
    """Run a command, return stripped stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _fmt_k(count: int) -> str:
    """Format a token count as '12.3k', '999', or '0'."""
    if count <= 0:
        return "0"
    if count < 1000:
        return str(count)
    return f"{count / 1000:.1f}k"


def _abbrev_home(path: str) -> str:
    """Replace the $HOME prefix with ~."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


# ---------------------------------------------------------------------------
# Section 1: git context
# ---------------------------------------------------------------------------


def git_section() -> str:
    """Return e.g. 'generic-ml-cache  main  a3b7c8  ±4'."""
    branch = _run(["git", "branch", "--show-current"])
    if not branch:
        return ""

    repo_root = _run(["git", "rev-parse", "--show-toplevel"])
    repo_name = os.path.basename(repo_root) if repo_root else ""
    short_hash = _run(["git", "rev-parse", "--short", "HEAD"])

    porcelain = _run(["git", "status", "--porcelain"])
    dirty_count = (
        len([l for l in porcelain.splitlines() if l.strip()]) if porcelain else 0
    )

    parts = []
    if repo_name:
        parts.append(repo_name)
    if branch:
        parts.append(branch)
    if short_hash:
        parts.append(short_hash)
    if dirty_count > 0:
        parts.append(f"±{dirty_count}")

    return "  ".join(parts)


# ---------------------------------------------------------------------------
# Section 2: current working directory
# ---------------------------------------------------------------------------


def cwd_section() -> str:
    """Return abbreviated path of the current working directory."""
    return _abbrev_home(os.getcwd())


# ---------------------------------------------------------------------------
# Section 3: gmlcache session stats
# ---------------------------------------------------------------------------


def cache_section() -> str:
    """Return e.g. 'abc123ef  [ci]  ▶42 ✓18 43%  sonnet  ↑12.3k ↓8.1k ⚡2.0k ✎500'."""
    raw = _run(["gmlcache", "status-line"], timeout=3)
    if not raw:
        return ""

    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    session_id: str = data.get("session_id", "")
    short_id = session_id[:8] if session_id else ""
    tags: list[str] = data.get("tags", [])
    calls: int = data.get("calls", 0)
    hits: int = data.get("hits", 0)
    hit_rate: float = data.get("hit_rate", 0.0)
    by_model: list[dict] = data.get("by_model", [])

    tag_str = f"[{', '.join(tags)}]  " if tags else ""
    hit_pct = int(hit_rate * 100)
    headline = f"{short_id}  {tag_str}▶{calls} ✓{hits} {hit_pct}%"

    model_parts: list[str] = []
    for row in by_model:
        label = row.get("model", "?")
        spent_in = row.get("spent_input", 0)
        spent_out = row.get("spent_output", 0)
        cache_read = row.get("cache_read_tokens", 0)
        cache_write = row.get("cache_write_tokens", 0)
        reasoning = row.get("reasoning_tokens", 0)

        tokens = f"↑{_fmt_k(spent_in)} ↓{_fmt_k(spent_out)}"
        if cache_read > 0:
            tokens += f" ⚡{_fmt_k(cache_read)}"
        if cache_write > 0:
            tokens += f" ✎{_fmt_k(cache_write)}"
        if reasoning > 0:
            tokens += f" ∿{_fmt_k(reasoning)}"

        model_parts.append(f"{label}  {tokens}")

    if model_parts:
        return headline + "  │  " + "  │  ".join(model_parts)
    return headline


# ---------------------------------------------------------------------------
# Section 4: Claude quota (ctt)
# ---------------------------------------------------------------------------


def quota_section() -> str:
    """Return the ctt one-liner, e.g. '4h 17m $1.24'.

    ctt (https://github.com/StaticB1/claude_ai_usage_widget) shows the
    5-hour rolling window burn.  --no-cloud uses only local logs.
    """
    return _run(["ctt", "prompt", "--no-cloud"], timeout=4)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    sections = []

    git = git_section()
    if git:
        sections.append(git)

    cwd = cwd_section()
    if cwd:
        sections.append(cwd)

    cache = cache_section()
    if cache:
        sections.append(cache)

    quota = quota_section()
    if quota:
        sections.append(quota)

    if sections:
        print(_SEP.join(sections))


if __name__ == "__main__":
    main()
