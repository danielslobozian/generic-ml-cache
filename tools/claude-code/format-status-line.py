#!/usr/bin/env python3
"""format-status-line.py — readable Claude Code status-line formatter.

Design goals:
  - Understandable without a legend/documentation.
  - Stable in two modes:
      1. without a gmlcache session
      2. with a gmlcache session
  - Optional PR/MR line appears only when a PR/MR exists.
  - Optional cache/model lines appear only when gmlcache reports a session.
  - Long branch names, paths, tags, model names, etc. are clipped predictably.

Output shape:

  Without session:
    git <repo>/<branch> <hash> dirty:<n>  │  📁 <cwd>  │  quota 5h <pct>/<reset> · wk <pct>/<reset>
    PR #123  ✗1 ✓12 …2 💬4                 # only if a PR/MR exists

  With session:
    git <repo>/<branch> <hash> dirty:<n>  │  📁 <cwd>  │  quota 5h <pct>/<reset> · wk <pct>/<reset>
    PR #123  ✗1 ✓12 …2 💬4                 # only if a PR/MR exists
    cache <session> [tags] hits <hits>/<calls> <pct>%
      model <name> in:<tokens> out:<tokens> cache-r:<tokens> cache-w:<tokens> think:<tokens>

Usage — copy tools/claude-code/settings.json to .claude/settings.json, or add
manually:
  {
    "statusLine": {
      "type": "command",
      "command": "python3 $(git rev-parse --show-toplevel)/tools/claude-code/format-status-line.py",
      "refreshInterval": 30
    }
  }
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SEP = "  │  "
_GMLCACHE_BIN = "gmlcache"

# Width budgets. These are deliberately conservative because the Claude Code
# status area is narrow and constantly refreshed.
MAX_REPO = 24
MAX_BRANCH = 42
MAX_CWD = 56
MAX_TAGS = 30
MAX_MODEL = 18
MAX_SESSION_ID = 10
MAX_FINAL_LINE = 180


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


def _strip_ansi(text: str) -> str:
    """Remove ANSI/OSC sequences for rough width calculations."""
    # OSC 8 hyperlinks and similar: ESC ] ... BEL or ESC ] ... ESC \\
    text = re.sub(r"\x1b\].*?(?:\x07|\x1b\\\\)", "", text)
    # CSI colours etc.
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _visible_len(text: str) -> int:
    """Approximate visible width. Good enough for ASCII-heavy status text."""
    return len(_strip_ansi(text))


def _hyperlink(url: str, text: str) -> str:
    """Wrap text in an OSC 8 terminal hyperlink."""
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


def _clip_end(text: str, max_len: int) -> str:
    """Clip text at the end: very-long-name -> very-long-na…."""
    if not text or _visible_len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return _strip_ansi(text)[: max_len - 1] + "…"


def _clip_middle(text: str, max_len: int) -> str:
    """Clip text in the middle: feature/foo/bar -> feature/…/bar."""
    plain = _strip_ansi(text)
    if not plain or len(plain) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    left = (max_len - 1) // 2
    right = max_len - 1 - left
    return plain[:left] + "…" + plain[-right:]


def _clip_path(path: str, max_len: int = MAX_CWD) -> str:
    """Keep the useful tail of a path while preserving ~ or / when possible."""
    path = _abbrev_home(path)
    if len(path) <= max_len:
        return path

    sep = os.sep
    if path.startswith("~"):
        prefix = "~"
        rest = path[2:] if path.startswith("~/") else path[1:]
    elif path.startswith(sep):
        prefix = sep
        rest = path[1:]
    else:
        prefix = ""
        rest = path

    parts = [part for part in rest.split(sep) if part]
    if not parts:
        return _clip_middle(path, max_len)

    tail: list[str] = []
    best = ""
    for part in reversed(parts):
        candidate_tail = sep.join([part] + tail)
        if prefix == "~":
            candidate = f"~/…/{candidate_tail}"
        elif prefix == sep:
            candidate = f"/…/{candidate_tail}"
        else:
            candidate = f"…/{candidate_tail}"

        if len(candidate) > max_len:
            break
        tail.insert(0, part)
        best = candidate

    return best or _clip_middle(path, max_len)


def _fit_line(line: str, max_width: int = MAX_FINAL_LINE) -> str:
    """Emergency final guard. Per-field budgets should do most of the work."""
    if _visible_len(line) <= max_width:
        return line
    return _clip_end(line, max_width)


# ---------------------------------------------------------------------------
# Section 1: git context
# ---------------------------------------------------------------------------


def git_section() -> str:
    """Return e.g. 'git generic-ml-cache/main a3b7c8 dirty:4'."""
    branch = _run(["git", "branch", "--show-current"])
    if not branch:
        return ""

    repo_root = _run(["git", "rev-parse", "--show-toplevel"])
    repo_name = os.path.basename(repo_root) if repo_root else ""
    short_hash = _run(["git", "rev-parse", "--short", "HEAD"])

    porcelain = _run(["git", "status", "--porcelain"])
    dirty_count = (
        len([ln for ln in porcelain.splitlines() if ln.strip()]) if porcelain else 0
    )

    repo_label = _clip_end(repo_name, MAX_REPO) if repo_name else "?"
    branch_label = _clip_middle(branch, MAX_BRANCH)

    parts = [f"git {repo_label}/{branch_label}"]
    if short_hash:
        parts.append(short_hash)
    if dirty_count > 0:
        parts.append(f"dirty:{dirty_count}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Section 2: current working directory
# ---------------------------------------------------------------------------


def cwd_section(cc_data: dict) -> str:
    """Return e.g. '📁 ~/…/generic-ml-cache/src'."""
    cwd = (
        (cc_data.get("workspace") or {}).get("current_dir")
        or cc_data.get("cwd")
        or os.getcwd()
    )
    return "📁 " + _clip_path(cwd)


# ---------------------------------------------------------------------------
# Section 3: gmlcache session stats
# ---------------------------------------------------------------------------


def _session_label(session_id: str) -> str:
    """Short but recognizable session ID."""
    if not session_id:
        return "?"
    if "-" in session_id:
        return _clip_end(session_id.split("-")[0] + "-…", MAX_SESSION_ID)
    return _clip_end(session_id, MAX_SESSION_ID)


def _fmt_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    return "[" + _clip_end(", ".join(tags), MAX_TAGS) + "] "


def _model_label(model: str) -> str:
    """Normalize common Claude model names; clip unknown provider names."""
    model = model or "?"
    lower = model.lower()
    if "opus" in lower:
        return "opus"
    if "sonnet" in lower:
        return "sonnet"
    if "haiku" in lower:
        return "haiku"
    return _clip_end(model, MAX_MODEL)


def cache_sections() -> tuple[str, list[str]]:
    """Return (cache headline, model detail lines). Empty headline means no session."""
    raw = _run([_GMLCACHE_BIN, "status-line"], timeout=3)
    if not raw:
        return "", []

    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError:
        return "", []

    session_id: str = data.get("session_id", "")
    tags: list[str] = data.get("tags", [])
    calls: int = data.get("calls", 0)
    hits: int = data.get("hits", 0)
    hit_rate: float = data.get("hit_rate", 0.0)
    by_model: list[dict] = data.get("by_model", [])

    hit_pct = int(hit_rate * 100)
    headline = (
        f"cache {_session_label(session_id)} "
        f"{_fmt_tags(tags)}hits {hits}/{calls} {hit_pct}%"
    )

    model_lines: list[str] = []
    for row in by_model:
        label = _model_label(row.get("model", "?"))
        spent_in = row.get("spent_input", 0)
        spent_out = row.get("spent_output", 0)
        cache_read = row.get("cache_read_tokens", 0)
        cache_write = row.get("cache_write_tokens", 0)
        reasoning = row.get("reasoning_tokens", 0)

        token_parts = [
            f"in:{_fmt_k(spent_in)}",
            f"out:{_fmt_k(spent_out)}",
        ]
        if cache_read > 0:
            token_parts.append(f"cache-r:{_fmt_k(cache_read)}")
        if cache_write > 0:
            token_parts.append(f"cache-w:{_fmt_k(cache_write)}")
        if reasoning > 0:
            token_parts.append(f"think:{_fmt_k(reasoning)}")

        model_lines.append(f"  model {label} " + " ".join(token_parts))

    return headline, model_lines


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


def _fmt_reset_ts(epoch: float) -> str:
    """Format a Unix-epoch reset timestamp as a human duration from now."""
    if not epoch:
        return ""
    secs = max(int(epoch - time.time()), 0)
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h >= 24:
        d, rh = divmod(h, 24)
        return f"{d}d{rh}h"
    return f"{h}h{m:02d}m" if h else f"{m}m"


def _fmt_quota_part(label: str, pct: int, reset: str) -> str:
    return f"{label} {pct}%/{reset}" if reset else f"{label} {pct}%"


def _quota_section_api() -> str:
    """Fallback: fetch rate-limit data from the Anthropic usage API.
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

    parts = []
    if five:
        parts.append(_fmt_quota_part("5h", _pct(five), _fmt_reset(five.get("resets_at", ""))))
    if seven:
        parts.append(_fmt_quota_part("wk", _pct(seven), _fmt_reset(seven.get("resets_at", ""))))

    line = "quota " + " · ".join(parts) if parts else ""
    try:
        _QUOTA_CACHE.write_text(json.dumps({"ts": time.time(), "line": line}))
    except OSError:
        pass
    return line


def quota_section(cc_data: dict) -> str:
    """Return e.g. 'quota 5h 12%/3h59m · wk 6%/6d7h'.

    Reads from Claude Code's stdin JSON first — instant, no HTTP, no OAuth.
    Falls back to the Anthropic usage API for older Claude Code versions or
    sessions where rate_limits is absent (non-Pro/Max).
    """
    rate_limits = cc_data.get("rate_limits") or {}
    five = rate_limits.get("five_hour") or {}
    seven = rate_limits.get("seven_day") or {}

    if five or seven:
        parts = []
        if five:
            p5 = round(five.get("used_percentage", 0) or 0)
            r5 = _fmt_reset_ts(five.get("resets_at", 0))
            parts.append(_fmt_quota_part("5h", p5, r5))
        if seven:
            p7 = round(seven.get("used_percentage", 0) or 0)
            r7 = _fmt_reset_ts(seven.get("resets_at", 0))
            parts.append(_fmt_quota_part("wk", p7, r7))
        return "quota " + " · ".join(parts) if parts else ""

    return _quota_section_api()


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
        ["gh", "pr", "view", "--json", "number,url,comments,statusCheckRollup,state"],
        timeout=5,
    )
    if not raw:
        return ""
    try:
        pr: dict = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    if pr.get("state", "OPEN") != "OPEN":
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

    red = "\033[91m"
    green = "\033[92m"
    yellow = "\033[93m"
    reset = "\033[0m"

    label = _hyperlink(url, f"#{number}") if url else f"#{number}"
    parts: list[str] = [f"PR {label}"]
    if failed:
        parts.append(f"{red}✗{failed}{reset}")
    if passed:
        parts.append(f"{green}✓{passed}{reset}")
    if pending:
        parts.append(f"{yellow}…{pending}{reset}")
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
        "…" if pipeline_status in ("running", "pending", "waiting_for_resource") else "",
    )

    label = _hyperlink(url, f"!{number}") if url else f"!{number}"
    parts: list[str] = [f"MR {label}"]
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

    if not line:
        # PR closed/merged or no PR — clear stale cache immediately.
        try:
            _PR_CACHE.unlink(missing_ok=True)
        except OSError:
            pass
        return ""

    # Only cache when we have check data — an empty checks result is transient
    # (PR just opened, CI not yet queued) and not worth freezing for _PR_TTL.
    has_checks = any(c in line for c in ("✓", "✗", "…"))
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
    try:
        cc_data: dict = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        cc_data = {}

    # Line 1: always-visible project context.
    line1: list[str] = []
    for seg in (git_section(), cwd_section(cc_data), quota_section(cc_data)):
        if seg:
            line1.append(seg)
    if line1:
        print(_fit_line(_SEP.join(line1)))

    # Line 2: PR/MR only when a PR/MR exists.
    pr = pr_section()
    if pr:
        print(_fit_line(pr))

    # Lines 3+: cache/session only when gmlcache reports a session.
    cache_headline, model_lines = cache_sections()
    if cache_headline:
        print(_fit_line(cache_headline))
        for model_line in model_lines:
            print(_fit_line(model_line))


if __name__ == "__main__":
    main()
