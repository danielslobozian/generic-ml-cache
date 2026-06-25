# gmlcache demo — sessions: group a workflow's runs, then report on them.
#
# Render:   python3 docs/render-tape.py docs/sessions.tape
#        or: vhs docs/sessions.tape   (if gmlcache is already on PATH with a cold store)
#
# Requires: vhs + the `gmlcache` command on PATH, and a client named `claude`
#   on PATH (any executable that prints an answer). Start from a COLD store so
#   the first run is a real miss; the repeat is a cache hit.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-sessions.gif

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

# 1) Start a session — gmlcache generates the id; GMLCACHE_SESSION tags every run below.
Type "export GMLCACHE_SESSION=$(gmlcache session start)"  Enter
Sleep 500ms
Type "echo $GMLCACHE_SESSION"  Enter
Sleep 1600ms

# 2) Run calls in the session. The misses are real calls; the identical repeat is a hit.
# Sleeps are tuned for real-client latency (a miss takes seconds; a hit is instant).
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"  Enter
Sleep 7s
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"  Enter
Sleep 2500ms
Type "gmlcache run --client claude --model sonnet --prompt 'Explain LRU in one line.'"  Enter
Sleep 7s

# 3) Report the session — invocations, executions (real calls), hits (served from cache).
Type "gmlcache session report $GMLCACHE_SESSION"  Enter
Sleep 4s
