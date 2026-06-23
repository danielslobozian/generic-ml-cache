# gmlcache demo — at-rest encryption: enable it, then watch the store lock.
#
# Render:   vhs docs/encrypt.tape   ->   docs/images/gmlcache-encrypt.gif
#
# Requires: vhs + the `gmlcache` command on PATH (built with the [encryption] extra),
#   and a client named `claude` on PATH. Start from a COLD, public store.
#
# The prompt is forced to a neutral `gmlcache ❯`, so no username/hostname shows.

Output docs/images/gmlcache-encrypt.gif

Require gmlcache

Set Shell bash
Set FontSize 26
Set Width 1700
Set Height 1180
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# 1) Record a call into a public store.
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"  Enter
Sleep 2000ms
Type "gmlcache status | grep encryption"  Enter
Sleep 1600ms

# 2) Encrypt — gmlcache generates the token (shown once), then locks the store.
Type "gmlcache encrypt"  Enter
Sleep 3200ms
Type "gmlcache status | grep encryption"  Enter
Sleep 1600ms

# 3) Without the token, even gmlcache cannot read the cache.
Type "gmlcache run --client claude --model sonnet --prompt 'Write a haiku about caching.'"  Enter
Sleep 3500ms
