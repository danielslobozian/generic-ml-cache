# gmlcache demo — scheduled stale eviction: daemon sweeps out entries older than max_age.
#
# Render:   python3 docs/render-tape.py docs/tapes/evict-stale.tape
#        or: vhs docs/tapes/evict-stale.tape   (if gmlcache is already on PATH with a cold store)
#
# render-tape.py installs gmlcache from source in an isolated tmp venv and store,
# and exports GMLCACHE_FAKE_CLAUDE — the enriched fake client echoes the prompt back,
# so the list output shows which entries were evicted.
#
# GMLCACHE_MAX_AGE=1 (1 second) and GMLCACHE_EVICTION_INTERVAL=3 are set in the
# hidden section so the daemon's first sweep (at t+3s) clears all entries immediately.
# No real API key is needed.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-evict-stale.gif

Require gmlcache

Set Shell bash
Set FontSize 28
Set Width 1700
Set Height 940
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: neutral prompt, 1-second max_age, 3-second sweep interval ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "export GMLCACHE_MAX_AGE=1"  Enter
Type "export GMLCACHE_EVICTION_INTERVAL=3"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Confirm max_age is active in the current config.
Type "gmlcache status"
Sleep 400ms
Enter
Sleep 2000ms

# 2) Record four entries into the store.
Type "gmlcache run --client claude --model sonnet --prompt 'What is a cache hit?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1000ms
Type "gmlcache run --client claude --model sonnet --prompt 'What is a cache miss?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1000ms
Type "gmlcache run --client claude --model sonnet --prompt 'Explain LRU in one line.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1000ms
Type "gmlcache run --client claude --model sonnet --prompt 'Why use a cache?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1000ms

# 3) Four entries are present and intact.
Type "gmlcache stats"  Enter
Sleep 1500ms
Type "gmlcache list"  Enter
Sleep 2000ms

# 4) Start the daemon in the background — it will sweep stale entries after GMLCACHE_EVICTION_INTERVAL seconds.
Type "gmlcache daemon start &"
Sleep 400ms
Enter
Type "export DAEMON_PID=$!"  Enter
Sleep 2500ms

# 5) Wait for the first sweep (interval = 3 s, max_age = 1 s — all entries are already stale).
Sleep 3500ms

# 6) Store is now empty — all four entries were evicted by the daemon.
Type "gmlcache stats"  Enter
Sleep 1500ms
Type "gmlcache list"  Enter
Sleep 2500ms

# 7) Confirm the daemon is still healthy, then stop it.
Type "gmlcache daemon status"  Enter
Sleep 1200ms
Type "kill $DAEMON_PID 2>/dev/null && echo 'daemon stopped'"  Enter
Sleep 1000ms
