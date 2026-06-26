# gmlcache demo — sessions: group a workflow's runs, tag them, then report.
#
# Render:   python3 docs/render-tape.py docs/tapes/sessions.tape
#        or: vhs docs/tapes/sessions.tape   (if gmlcache is already on PATH with a cold store)
#
# render-tape.py installs gmlcache from source in an isolated tmp venv and store,
# and exports GMLCACHE_FAKE_CLAUDE — a fake executable so no real API key is needed.
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

# 1) Start session A with a tag — the id is captured into GMLCACHE_SESSION.
Type "export GMLCACHE_SESSION=$(gmlcache session start --tag sprint-3)"  Enter
Sleep 500ms
Type "echo $GMLCACHE_SESSION"  Enter
Sleep 1600ms

# 2) Run two calls under session A (fake client, instant).
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms

# 3) Report session A — shows tag, invocations, hit.
Type "gmlcache session report $GMLCACHE_SESSION"  Enter
Sleep 2500ms

# 4) Start session B with the same tag, run one more call.
Type "export GMLCACHE_SESSION=$(gmlcache session start --tag sprint-3)"  Enter
Sleep 500ms
Type "gmlcache run --client claude --model sonnet --prompt 'Explain LRU in one line.' --executable $GMLCACHE_FAKE_CLAUDE"  Enter
Sleep 1500ms

# 5) Aggregate report across all sessions tagged sprint-3.
Type "gmlcache session report --tag sprint-3"  Enter
Sleep 3000ms

# 6) Add an extra tag to session B, then remove the original one.
Type "gmlcache session tag --add $GMLCACHE_SESSION released"  Enter
Sleep 1200ms
Type "gmlcache session tag --remove $GMLCACHE_SESSION sprint-3"  Enter
Sleep 1200ms
Type "gmlcache session report $GMLCACHE_SESSION"  Enter
Sleep 2500ms
