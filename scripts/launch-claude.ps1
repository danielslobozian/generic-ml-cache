#!/usr/bin/env pwsh
<#
.SYNOPSIS
Open a gmlcache session and launch Claude Code.

.DESCRIPTION
1. Creates a new gmlcache session (local, no daemon needed).
2. Exports GMLCACHE_SESSION so gmlcache run, status-line, etc. pick it up.
3. Starts the daemon in the background if it is not already running
   (the daemon is needed for format-status-line.py to show live stats).
4. Launches claude, forwarding exit codes back to the caller.

.PARAMETER Tag
Attach one or more tags to the new session (repeatable).

.PARAMETER ClaudeArgs
Arguments forwarded verbatim to the `claude` command.

.EXAMPLE
.\scripts\launch-claude.ps1 --Tag sprint-7
.\scripts\launch-claude.ps1 --Tag sprint-7 --Tag ci -- --model claude-opus-4-8
#>
param(
    [string[]] $Tag = @(),
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ClaudeArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command gmlcache -ErrorAction SilentlyContinue)) {
    Write-Error "launch-claude: 'gmlcache' not found on PATH"
    exit 1
}

# ── 1. create a new session ───────────────────────────────────────────────────
$sessionArgs = [System.Collections.Generic.List[string]]::new()
$sessionArgs.AddRange(@('session', 'start'))
foreach ($t in $Tag) {
    $sessionArgs.AddRange(@('--tag', $t))
}

$env:GMLCACHE_SESSION = (& gmlcache @sessionArgs 2>&1)
if ($LASTEXITCODE -ne 0) {
    Write-Error "launch-claude: 'gmlcache session start' failed (exit $LASTEXITCODE)"
    exit 1
}
Write-Host "gmlcache: session $env:GMLCACHE_SESSION started" -ForegroundColor DarkGray

# ── 2. ensure daemon is running (required for live status-line) ───────────────
& gmlcache daemon status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "gmlcache: starting daemon in background..." -ForegroundColor DarkGray
    Start-Process -NoNewWindow -FilePath 'gmlcache' -ArgumentList 'daemon', 'start'

    # poll until daemon responds, or give up after 5 s
    foreach ($attempt in 1..5) {
        Start-Sleep -Seconds 1
        & gmlcache daemon status 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
}

# ── 3. launch claude ──────────────────────────────────────────────────────────
& claude @ClaudeArgs
exit $LASTEXITCODE
