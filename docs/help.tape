# gmlcache demo — the banner and the command overview (`gmlcache --help`).
#
# Render:   vhs docs/help.tape   ->   docs/images/gmlcache-help.gif
# Requires: vhs + the `gmlcache` command on PATH. No client or store needed.

Output docs/images/gmlcache-help.gif

Require gmlcache

Set Shell bash
Set FontSize 22
Set Width 1680
Set Height 1720
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "clear"  Enter
Show
Sleep 600ms

Type "gmlcache --help"
Sleep 600ms
Enter
Sleep 5s
