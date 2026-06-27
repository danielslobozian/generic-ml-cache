#!/usr/bin/env python3
"""format-status-line.py — default gmlcache status-bar formatter.

Assembles a single status line from five independent sections:

  1. git    — ⎇  repo name, branch, HEAD hash, dirty-file count
  2. cache  — gmlcache session ID, calls/hits, per-model token usage
  3. pr     — ⤴  PR/MR number, CI check counts (✓/✗/⋯), comment count, URL
              Uses `gh` for GitHub repos, `glab` for GitLab. Silently
              omitted if neither CLI is available or no PR/MR is open.
              Results are cached for 30 s to avoid hitting the API on
              every status-bar refresh.
  4. cwd    — 📁  abbreviated current working directory
  5. quota  — ⏱  Claude 5-hour rolling window usage + time to reset

Each section is independent — if a source is unavailable it is silently
omitted. Claude Code renders only the first line of output, so everything
lives in one │-separated line.

CUSTOMISE: comment out any section you don't need, rearrange the order in
main(), or change the icon/format variables at the top of each section.

Usage — wire into Claude Code's status bar via .claude/settings.json:
  {
    "statusLine": "python3 $(git rev-parse --show-toplevel)/scripts/format-status-line.py"
  }
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SEP = "  │  "

# Resolve the gmlcache binary: prefer the repo .venv so the dev version is
# used instead of whatever (possibly older) version is on the system PATH.
_GMLCACHE_BIN = "gmlcache"


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


def _hyperlink(url: str, text: str) -> str:
    """Wrap text in an OSC 8 terminal hyperlink. Renders as coloured, clickable text."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


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
    """Return e.g. '⎇ generic-ml-cache  main  a3b7c8  ±4'."""
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

    parts = ["⎇"]
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
    """Return e.g. '📁 ~/my-work/python/generic-ml-cache'."""
    return "📁  " + _abbrev_home(os.getcwd())


# ---------------------------------------------------------------------------
# Section 3: gmlcache session stats
# ---------------------------------------------------------------------------


def cache_section() -> str:
    """Return e.g. 'abc123ef  [ci]  ▶42 ✓18 43%  sonnet  ↑12.3k ↓8.1k ⚡2.0k ✎500'."""
    raw = _run([_GMLCACHE_BIN, "status-line"], timeout=3)
    if not raw:
        return ""

    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    session_id: str = data.get("session_id", "")
    # Show first UUID segment + ellipsis so it's recognisable against --resume output
    short_id = (session_id.split("-")[0] + "-…") if "-" in session_id else session_id[:8]
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
# Section 4: Claude quota (5-hour window + 7-day) via Anthropic usage API
# ---------------------------------------------------------------------------

_USAGE_API = "https://api.anthropic.com/api/oauth/usage"  # NOSONAR
_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
_QUOTA_CACHE = Path(tempfile.gettempdir()) / "gmlcache-claude-quota.json"
_QUOTA_TTL = 60  # seconds between API calls


def _oauth_token() -> str:
    try:
        data = json.loads(_CREDENTIALS.read_text())
        return data.get("claudeAiOauth", {}).get("accessToken", "")
    except (OSError, json.JSONDecodeError):
        return ""


def _fetch_quota(token: str) -> dict:
    req = urllib.request.Request(
        _USAGE_API,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:  # NOSONAR
        return json.loads(resp.read())


def _fmt_reset(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        secs = max(int((dt - datetime.now(timezone.utc)).total_seconds()), 0)
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h >= 24:
            d, rh = divmod(h, 24)
            return f"{d}d{rh}h"
        return f"{h}h{m:02d}m" if h else f"{m}m"
    except ValueError:
        return ""


def quota_section() -> str:
    """Return e.g. '3% : 4h45m  ·  65% 1d4h' from the Anthropic usage API.
    Results are cached for 60 s so the API is not called on every refresh.
    """
    try:
        cached = json.loads(_QUOTA_CACHE.read_text())
        if time.time() - cached.get("ts", 0) < _QUOTA_TTL:
            return cached.get("line", "")
    except (OSError, json.JSONDecodeError):
        pass

    token = _oauth_token()
    if not token:
        return ""

    try:
        data = _fetch_quota(token)
    except Exception:
        return ""

    def _pct(bucket: dict) -> int:
        u = bucket.get("utilization", 0)
        return round(u)

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}

    p5, r5 = _pct(five), _fmt_reset(five.get("resets_at", ""))
    p7, r7 = _pct(seven), _fmt_reset(seven.get("resets_at", ""))

    parts = []
    if five:
        parts.append(f"{p5}% : {r5}" if r5 else f"{p5}%")
    if seven:
        parts.append(f"{p7}% {r7}" if r7 else f"{p7}%")

    line = "⏱  " + "  ·  ".join(parts)
    try:
        _QUOTA_CACHE.write_text(json.dumps({"ts": time.time(), "line": line}))
    except OSError:
        pass
    return line


# ---------------------------------------------------------------------------
# Section 5: pull request / merge request status (gh or glab)
# ---------------------------------------------------------------------------

_PR_CACHE = Path(tempfile.gettempdir()) / "gmlcache-pr-status.json"
_PR_TTL = 10  # seconds between gh/glab API calls


def _cmd_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _github_pr_section() -> str:
    """Return PR status for the current branch using the gh CLI."""
    raw = _run(
        ["gh", "pr", "view", "--json", "number,url,comments,statusCheckRollup"],
        timeout=5,
    )
    if not raw:
        return ""
    try:
        pr: dict = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    number = pr.get("number", "")
    url = pr.get("url", "")
    comments = pr.get("comments") or []
    checks = pr.get("statusCheckRollup") or []

    passed = sum(
        1 for c in checks
        if c.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED")
    )
    failed = sum(
        1 for c in checks
        if c.get("conclusion") in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED")
    )
    pending = sum(
        1 for c in checks
        if c.get("status") in ("IN_PROGRESS", "QUEUED", "WAITING", "PENDING")
        and not c.get("conclusion")
    )

    _RED    = "\033[91m"
    _GREEN  = "\033[92m"
    _YELLOW = "\033[93m"
    _RESET  = "\033[0m"

    label = _hyperlink(url, f"#{number}") if url else f"#{number}"
    parts: list[str] = [f"⤴  {label}"]
    if failed:
        parts.append(f"{_RED}✗{failed}{_RESET}")
    if passed:
        parts.append(f"{_GREEN}✓{passed}{_RESET}")
    if pending:
        parts.append(f"{_YELLOW}⋯ {pending}{_RESET}")
    if comments:
        parts.append(f"💬{len(comments)}")

    return "  ".join(parts)


def _gitlab_mr_section() -> str:
    """Return MR status for the current branch using the glab CLI."""
    raw = _run(["glab", "mr", "view", "--output", "json"], timeout=5)
    if not raw:
        return ""
    try:
        mr: dict = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    number = mr.get("iid") or mr.get("id", "")
    url = mr.get("web_url", "")
    notes = mr.get("user_notes_count", 0)
    pipeline = mr.get("pipeline") or {}
    pipeline_status = pipeline.get("status", "")

    check_icon = {"success": "✓", "failed": "✗", "canceled": "✗"}.get(
        pipeline_status,
        "⋯" if pipeline_status in ("running", "pending", "waiting_for_resource") else "",
    )

    label = _hyperlink(url, f"!{number}") if url else f"!{number}"
    parts: list[str] = [f"⤴  {label}"]
    if check_icon:
        parts.append(check_icon)
    if notes:
        parts.append(f"💬{notes}")

    return "  ".join(parts)


def pr_section() -> str:
    """Return PR/MR info, cached for _PR_TTL seconds to avoid hammering the API."""
    try:
        cached = json.loads(_PR_CACHE.read_text())
        if time.time() - cached.get("ts", 0) < _PR_TTL:
            return cached.get("line", "")
    except (OSError, json.JSONDecodeError):
        pass

    if _cmd_exists("gh"):
        line = _github_pr_section()
    elif _cmd_exists("glab"):
        line = _gitlab_mr_section()
    else:
        return ""

    # Only cache when we have check data — an empty checks result is transient
    # (PR just opened, CI not yet queued) and not worth freezing for 30 s.
    has_checks = any(c in line for c in ("✓", "✗", "⋯"))
    if has_checks:
        try:
            _PR_CACHE.write_text(json.dumps({"ts": time.time(), "line": line}))
        except OSError:
            pass
    return line


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    sections: list[str] = []

    git = git_section()
    if git:
        sections.append(git)

    cache = cache_section()
    if cache:
        sections.append(cache)

    pr = pr_section()
    if pr:
        sections.append(pr)

    cwd = cwd_section()
    if cwd:
        sections.append(cwd)

    quota = quota_section()
    if quota:
        sections.append(quota)

    if sections:
        print(_SEP.join(sections))


if __name__ == "__main__":
    main()
