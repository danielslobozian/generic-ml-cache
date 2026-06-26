# gmlcache demo — daemon: start the HTTP API, hit endpoints, stop.
#
# Render:   python3 docs/render-tape.py docs/tapes/daemon.tape
#
# render-tape.py installs core + cli + daemon from source in an isolated tmp venv
# and store, sets GMLCACHE_FAKE_CLAUDE, and exports GMLCACHE_CONFIG.
# No real API key is needed — the store is pre-populated with fake executions.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-daemon.gif

Require gmlcache

Set Shell bash
Set FontSize 24
Set Width 1900
Set Height 1340
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: populate store, create a session, start daemon in background ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter

Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 800ms
Type "gmlcache run --client claude --model sonnet --prompt 'Explain LRU eviction in one sentence.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 800ms
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 800ms
Type "export SID=$(gmlcache session start --tag api-demo)"  Enter
Sleep 400ms

Type "gmlcache daemon start &"  Enter
Type "export DAEMON_PID=$!"  Enter
Type "sleep 2"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Confirm the daemon is reachable via the CLI health check.
Type "gmlcache daemon status"
Sleep 600ms
Enter
Sleep 1600ms

# 2) Raw liveness endpoint.
Type "curl -s http://127.0.0.1:8765/health"
Sleep 600ms
Enter
Sleep 1200ms

# 3) Info: version, store path, adapters.
Type "curl -s http://127.0.0.1:8765/info | python3 -m json.tool"
Sleep 600ms
Enter
Sleep 1800ms

# 4) Executions already in the store (recorded by CLI above).
Type "curl -s http://127.0.0.1:8765/executions | python3 -m json.tool"
Sleep 600ms
Enter
Sleep 1800ms

# 5) Global stats: total executions + cache hit count.
Type "curl -s http://127.0.0.1:8765/stats | python3 -m json.tool"
Sleep 600ms
Enter
Sleep 1600ms

# 6) Sessions — the one created above is visible.
Type "curl -s http://127.0.0.1:8765/sessions | python3 -m json.tool"
Sleep 600ms
Enter
Sleep 1500ms

# 7) Create a new session via the API directly.
Type "curl -s -X POST http://127.0.0.1:8765/sessions \\"
Sleep 300ms
Enter
Type "     -H 'Content-Type: application/json' \\"
Sleep 300ms
Enter
Type "     -d '{\"tags\":[\"web-demo\"]}' | python3 -m json.tool"
Sleep 600ms
Enter
Sleep 2200ms

# 8) Stop the daemon.
Type "kill $DAEMON_PID 2>/dev/null && echo 'daemon stopped'"
Sleep 600ms
Enter
Sleep 1000ms
