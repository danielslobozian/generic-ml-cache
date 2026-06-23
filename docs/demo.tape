# gmlcache demo — help, then the same command twice: first calls the client, then hits cache.
#
# Render:   vhs docs/demo.tape   ->   docs/images/gmlcache-demo.gif
#
# Requires: vhs + the `gmlcache` command on PATH, with a real client (claude here)
#           installed and authenticated.
#
# IMPORTANT: start from a COLD cache so the first run is a real miss. Clear the store
#   (its path is shown by `gmlcache status`) then run `vhs docs/demo.tape`.
#
# Crispness: the asset is rendered large; display it at ~50% width so it stays
# sharp (a downsampled "retina" asset).
#
# Tune: swap CLIENT/MODEL/PROMPT to a client you have; adjust the `Sleep 9s` after
# the first run to your client's real latency. `vhs themes` lists themes.
#
# gmlcache adds nothing to the client's output; timing is shown by the shell's
# `time`, never by gmlcache (the cache stays a transparent drop-in). The prompt is
# forced to a neutral `gmlcache ❯`, so no username/hostname appears.

Output docs/images/gmlcache-demo.gif

Require gmlcache

Set Shell bash
Set FontSize 28
Set Width 1920
Set Height 1200
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

# --- hidden setup: neutral prompt, one-line time format, clean screen ---
Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "export TIMEFORMAT='   ⏱  %Rs'"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 0) What can it do? — the help menu, briefly, then clear for the value demo.
Type "gmlcache --help"
Sleep 600ms
Enter
Sleep 3500ms
Hide
Type "clear"  Enter
Show
Sleep 400ms

# 1) Not cached yet — `check` reports a miss without calling anything.
Type "gmlcache check --client claude --model sonnet --prompt 'Write a haiku about caching.'"
Sleep 600ms
Enter
Sleep 1800ms

# 2) First run — calls the real client and records it. The slow one.
Type "time gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"
Sleep 600ms
Enter
Sleep 9s

# 3) Now it is cached — `check` reports a hit.
Type "gmlcache check --client claude --model sonnet --prompt 'Write a haiku about caching.'"
Sleep 600ms
Enter
Sleep 1800ms

# 4) Same command again — served from cache, instant, byte-identical output.
Type "time gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"
Sleep 600ms
Enter
Sleep 4s
