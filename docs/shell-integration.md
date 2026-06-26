# Shell integration examples

This page shows how to wire gmlcache into your shell so that launching Claude Code
automatically creates a session and routes API calls through the local cache gateway.
It also shows how to enable the optional live status bar inside Claude Code.

These are **examples you adapt to your own setup** — not maintained scripts that ship
as part of gmlcache. Copy what fits, ignore what doesn't, and adjust paths for your
environment.

---

## Gateway launcher

The pattern is always the same regardless of platform:

1. Create a gmlcache session (`gmlcache session start`).
2. Start (or restart) the daemon.
3. Set `ANTHROPIC_BASE_URL` to `http://127.0.0.1:8765/gateway/claude/<session-id>`.
4. Launch `claude`.

The examples below package those steps into a single shell function.

### Linux and macOS — bash / zsh

Add to `~/.bashrc`, `~/.bash_profile`, or `~/.zshrc`:

```bash
cc() {
    local _gmlcache
    _gmlcache=$(which gmlcache 2>/dev/null) || { echo "cc: gmlcache not found on PATH" >&2; return 1; }

    # parse --tag flags; everything else goes to claude
    local _session_tags=() _claude_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag)   _session_tags+=(--tag "$2"); shift 2 ;;
            --tag=*) _session_tags+=(--tag "${1#--tag=}"); shift ;;
            *)       _claude_args+=("$1"); shift ;;
        esac
    done

    # create session
    local _session
    _session=$("$_gmlcache" session start "${_session_tags[@]}") || return 1
    echo "gmlcache: session ${_session} started" >&2

    # (re)start daemon
    "$_gmlcache" daemon status >/dev/null 2>&1 && "$_gmlcache" daemon stop 2>/dev/null || true
    local _store
    _store=$("$_gmlcache" status --json 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['settings']['store']['value'])" 2>/dev/null \
        || echo "$TMPDIR")
    "$_gmlcache" daemon start >>"${_store}/daemon.log" 2>&1 &
    local _i; for _i in 1 2 3 4 5; do
        sleep 1; "$_gmlcache" daemon status >/dev/null 2>&1 && break
    done

    # launch claude through the gateway
    GMLCACHE_SESSION="$_session" \
    ANTHROPIC_BASE_URL="http://127.0.0.1:8765/gateway/claude/${_session}" \
    claude --session-id "$_session" "${_claude_args[@]}"
}
```

**Examples**

```bash
cc                              # plain session
cc --tag PROJ-42                # tag the session with a ticket number
cc --tag feature --tag backend  # multiple tags
```

After `claude` exits you are back at your prompt. The daemon keeps running, so
`gmlcache session report <id>` and `gmlcache list` work against the completed session.

### Windows — PowerShell

Add to your PowerShell profile (`$PROFILE`):

```powershell
function cc {
    param([string[]]$Tags = @(), [string[]]$ClaudeArgs = $args)

    $gmlcache = Get-Command gmlcache -ErrorAction SilentlyContinue
    if (-not $gmlcache) { Write-Error "cc: gmlcache not found on PATH"; return }

    # build session start args
    $sessionArgs = @('session', 'start')
    foreach ($tag in $Tags) { $sessionArgs += '--tag'; $sessionArgs += $tag }

    $session = & gmlcache @sessionArgs
    if (-not $session) { return }
    Write-Host "gmlcache: session $session started" -ForegroundColor DarkGray

    # (re)start daemon
    & gmlcache daemon stop 2>$null
    $store = (& gmlcache status --json | ConvertFrom-Json).settings.store.value
    Start-Process gmlcache -ArgumentList 'daemon','start' `
        -RedirectStandardOutput "$store\daemon.log" -WindowStyle Hidden
    1..5 | ForEach-Object {
        Start-Sleep 1
        if (& gmlcache daemon status 2>$null) { return }
    }

    # launch claude through the gateway
    $env:GMLCACHE_SESSION       = $session
    $env:ANTHROPIC_BASE_URL     = "http://127.0.0.1:8765/gateway/claude/$session"
    & claude --session-id $session @ClaudeArgs
    $env:GMLCACHE_SESSION       = $null
    $env:ANTHROPIC_BASE_URL     = $null
}
```

**Example**

```powershell
cc -Tags PROJ-42
```

---

## Claude Code status bar

`scripts/format-status-line.py` is a Python script that produces a single status
line by reading from git, the daemon API, and (optionally) the Claude quota API.
Wire it into Claude Code's `statusLine` setting in `.claude/settings.json`:

### Linux and macOS

```json
{
  "statusLine": "python3 /absolute/path/to/scripts/format-status-line.py"
}
```

### Windows

```json
{
  "statusLine": "python C:\\absolute\\path\\to\\scripts\\format-status-line.py"
}
```

The script uses only the Python standard library and is platform-neutral. Paths
that vary by OS are resolved at runtime (`pathlib.Path.home()`,
`tempfile.gettempdir()`), so the same file works on all three platforms unchanged.

---

## Claude quota display

When a Claude Code session is active, the status bar automatically shows your
Claude Max usage for the current 5-hour block and the 7-day rolling window:

```
3% : 3h58m  ·  66% 1d3h
```

- **Left** — 5-hour block: percentage used · time until reset.
- **Right** — 7-day window: percentage used · time until reset.

This reads the OAuth token that Claude Code writes to `~/.claude/.credentials.json`
(created automatically when you log in with `claude`). No separate configuration is
needed. The result is cached for 60 seconds so the API is not polled on every
status-bar refresh.

The quota display only appears when Claude Code is installed and you are logged in.
If the credentials file is absent or the API call fails, the section is silently
omitted.

---

## Daemon log

The daemon appends to `<store>/daemon.log` on each launch.

**Linux / macOS**

```bash
tail -f ~/.gmlcache/daemon.log
```

**Windows**

```powershell
Get-Content "$env:USERPROFILE\.gmlcache\daemon.log" -Wait
```
