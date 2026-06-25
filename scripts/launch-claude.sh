#!/usr/bin/env bash
# launch-claude.sh — open a gmlcache session and launch Claude Code.
#
# Usage:
#   ./scripts/launch-claude.sh [--tag TAG]... [-- CLAUDE_ARGS...]
#
#   --tag TAG    attach a tag to the new session (repeatable)
#   All other arguments are forwarded verbatim to the `claude` command.
#
# What it does:
#   1. Creates a new gmlcache session (local, no daemon needed)
#   2. Exports GMLCACHE_SESSION so gmlcache run, status-line, etc. pick it up
#   3. Starts the daemon in the background if it is not already running
#      (the daemon is needed for format-status-line.py to show live stats)
#   4. Exec's claude — replacing this shell process so signals and exit codes
#      propagate correctly

set -euo pipefail

if ! command -v gmlcache >/dev/null 2>&1; then
    echo "launch-claude: 'gmlcache' not found on PATH" >&2
    exit 1
fi

# ── parse our flags; collect the rest for claude ─────────────────────────────
session_tags=()
claude_args=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --)
            shift
            claude_args+=("$@")
            break
            ;;
        --tag)
            session_tags+=("$2")
            shift 2
            ;;
        --tag=*)
            session_tags+=("${1#--tag=}")
            shift
            ;;
        *)
            claude_args+=("$1")
            shift
            ;;
    esac
done

# ── 1. create a new session ───────────────────────────────────────────────────
session_cmd=(gmlcache session start)
for tag in "${session_tags[@]}"; do
    session_cmd+=(--tag "$tag")
done

GMLCACHE_SESSION=$("${session_cmd[@]}")
export GMLCACHE_SESSION
echo "gmlcache: session ${GMLCACHE_SESSION} started" >&2

# ── 2. ensure daemon is running (required for live status-line) ───────────────
if ! gmlcache daemon status >/dev/null 2>&1; then
    echo "gmlcache: starting daemon in background..." >&2
    gmlcache daemon start &

    # poll until daemon responds, or give up after 5 s
    for _attempt in 1 2 3 4 5; do
        sleep 1
        if gmlcache daemon status >/dev/null 2>&1; then
            break
        fi
    done
fi

# ── 3. launch claude ──────────────────────────────────────────────────────────
exec claude "${claude_args[@]}"
