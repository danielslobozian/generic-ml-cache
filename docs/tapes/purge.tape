# gmlcache demo — purge: reclaim space with soft purge by tag, then wipe with purge --all.
#
# Render:   python3 docs/render-tape.py docs/tapes/purge.tape
#        or: vhs docs/tapes/purge.tape   (if gmlcache is already on PATH)
#
# render-tape.sh installs gmlcache from source in an isolated tmp venv and store,
# and exports GMLCACHE_FAKE_CLAUDE — a fake executable so no real API key is needed.
# The fake script outputs plain text; the claude adapter stores it verbatim.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-purge.gif

Require gmlcache

Set Shell bash
Set FontSize 28
Set Width 1700
Set Height 940
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: neutral prompt, clean screen ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Record two executions with the demo tag using the fake executable.
Type "gmlcache run --client claude --model sonnet --tag demo --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms
Type "gmlcache run --client claude --model sonnet --tag demo --prompt 'Explain LRU eviction in one sentence.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms

# 2) stats: show execution count and current store size.
Type "gmlcache stats"  Enter
Sleep 2000ms

# 3) Soft-purge by tag — blobs freed, execution records and statistics preserved.
Type "gmlcache purge --tag demo"  Enter
Sleep 1500ms

# 4) stats again — store size smaller; history still there (soft purge kept records).
Type "gmlcache stats"  Enter
Sleep 2000ms

# 5) Record one more execution (no tag).
Type "gmlcache run --client claude --model sonnet --prompt 'What is a cache miss?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms

# 6) Wipe everything with purge --all — confirmation phrase required.
Type "gmlcache purge --all --confirm 'purge all'"  Enter
Sleep 1500ms

# 7) stats — empty store.
Type "gmlcache stats"  Enter
Sleep 2500ms
