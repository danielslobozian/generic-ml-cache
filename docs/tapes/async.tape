# gmlcache demo — detached executions: submit, check, watch, fetch the result.
#
# Render:   python3 docs/render-tape.py docs/tapes/async.tape
#        or: vhs docs/tapes/async.tape   (if gmlcache is already on PATH with a cold store)
#
# Requires: vhs + the `gmlcache` command on PATH, and a client named `claude` on PATH.
#   Start from a COLD store. The detached worker is a real gmlcache process, so `claude`
#   must be runnable from a fresh environment (no inherited CLAUDECODE).
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-async.gif

Require gmlcache

Set Shell bash
Set FontSize 24
Set Width 1900
Set Height 1280
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Submit a detached run — it returns an execution id immediately.
Type "JID=$(gmlcache run --client claude --model sonnet --grant web-search --prompt 'Search the web for the capital of France, then write a haiku about it.' --detach)"  Enter
Sleep 700ms
Type "echo $JID"  Enter
Sleep 1300ms

# 2) It is running in the background.
Type "gmlcache execution status $JID"  Enter
Sleep 1800ms

# 3) Follow the event log live — the client's own progress (thinking, tool calls) streams in.
Type "gmlcache execution watch $JID"  Enter
Sleep 16s

# 4) Fetch the recorded result.
Type "gmlcache execution result $JID"  Enter
Sleep 3s
