# gmlcache demo — LRU eviction: a size quota silently evicts the oldest entries.
#
# Render:   python3 docs/render-tape.py docs/tapes/evict-lru.tape
#        or: vhs docs/tapes/evict-lru.tape   (if gmlcache is already on PATH with a cold store)
#
# render-tape.py installs gmlcache from source in an isolated tmp venv and store,
# and exports GMLCACHE_FAKE_CLAUDE — the enriched fake client reads the prompt from
# stdin and echoes it back, so the list output shows which entries survived eviction.
#
# GMLCACHE_MAX_SIZE=100b is set in the hidden section so eviction kicks in after
# the third unique entry.  No real API key is needed.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-evict-lru.gif

Require gmlcache

Set Shell bash
Set FontSize 28
Set Width 1700
Set Height 940
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: neutral prompt, tight size quota ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "export GMLCACHE_MAX_SIZE=100b"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Confirm max_size is active in the current config.
Type "gmlcache status"
Sleep 400ms
Enter
Sleep 2000ms

# 2) Record three entries — all fit within the 100-byte quota.
Type "gmlcache run --client claude --model sonnet --prompt 'What is a cache hit?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms
Type "gmlcache run --client claude --model sonnet --prompt 'What is a cache miss?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms
Type "gmlcache run --client claude --model sonnet --prompt 'Explain LRU in one line.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms

# 3) All three entries are present — store is just under quota.
Type "gmlcache stats"  Enter
Sleep 1500ms
Type "gmlcache list"  Enter
Sleep 2500ms

# 4) Record three more entries — each one pushes past the quota and evicts the oldest.
Type "gmlcache run --client claude --model sonnet --prompt 'Why use a cache?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms
Type "gmlcache run --client claude --model sonnet --prompt 'How does eviction work?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms
Type "gmlcache run --client claude --model sonnet --prompt 'Name one eviction policy.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1200ms

# 5) Only the three newest entries remain — the three oldest were evicted automatically.
Type "gmlcache stats"  Enter
Sleep 1500ms
Type "gmlcache list"  Enter
Sleep 3000ms
