# gmlcache demo — browsing the store: list, tags, stats, inspect.
#
# Render:   python3 docs/render-tape.py docs/inspect.tape
#
# render-tape.py installs gmlcache from source in an isolated tmp venv and store,
# and exports GMLCACHE_FAKE_CLAUDE — no real API key is needed.
# The store is pre-populated in the hidden section.

Output docs/images/gmlcache-inspect.gif

Require gmlcache

Set Shell bash
Set FontSize 26
Set Width 1800
Set Height 1080
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: populate store with varied executions, capture a key ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter

Type "gmlcache run --client claude --model sonnet --tag tutorial --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 600ms
Type "gmlcache run --client claude --model sonnet --tag tutorial --prompt 'Explain LRU eviction in one sentence.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 600ms
Type "gmlcache run --client claude --model opus --tag reference --prompt 'What is a Bloom filter?' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 600ms
Type "gmlcache run --client claude --model sonnet --tag tutorial --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 600ms

Type "export DEMO_KEY=$(gmlcache list | awk 'NR==2{print $1}')"  Enter
Sleep 400ms
Type "clear"  Enter
Show
Sleep 600ms

# 1) List all stored executions — key, client, model, state.
Type "gmlcache list"
Sleep 600ms
Enter
Sleep 2200ms

# 2) All tags in the store.
Type "gmlcache tags"
Sleep 600ms
Enter
Sleep 1600ms

# 3) Filter by tag.
Type "gmlcache list --tag tutorial"
Sleep 600ms
Enter
Sleep 1800ms

# 4) Global store stats — execution count, hit count, bytes.
Type "gmlcache stats"
Sleep 600ms
Enter
Sleep 1800ms

# 5) Deep-inspect a single execution — all recorded fields.
Type "gmlcache inspect $DEMO_KEY"
Sleep 600ms
Enter
Sleep 2800ms
