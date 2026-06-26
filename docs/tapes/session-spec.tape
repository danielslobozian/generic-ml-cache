# gmlcache demo — session exec spec + tag management (new in 0.13.0).
#
# Render:   python3 docs/render-tape.py docs/tapes/session-spec.tape
#
# render-tape.py installs gmlcache from source in an isolated tmp venv and store.
# No real API key is needed — all operations are session metadata only.
#
# Shows: session start with --client/--model/--effort, tag --add, tag --remove,
# session update (swap spec), and session clear-spec.

Output docs/images/gmlcache-session-spec.gif

Require gmlcache

Set Shell bash
Set FontSize 26
Set Width 1800
Set Height 1080
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

# 1) Start a session, pinning adapter + model + effort from the outset.
Type "SESSION=$(gmlcache session start \\"
Sleep 300ms
Enter
Type "    --client anthropic --model claude-haiku-4-5-20251001 --effort low \\"
Sleep 300ms
Enter
Type "    --tag sprint-4)"
Sleep 600ms
Enter
Sleep 400ms
Type "echo $SESSION"
Enter
Sleep 1400ms

# 2) Report shows the spec alongside the tag.
Type "gmlcache session report $SESSION"
Sleep 600ms
Enter
Sleep 2200ms

# 3) Add a second tag.
Type "gmlcache session tag --add $SESSION experiment"
Sleep 600ms
Enter
Sleep 1300ms

# 4) Remove the first tag (new in 0.13.0).
Type "gmlcache session tag --remove $SESSION sprint-4"
Sleep 600ms
Enter
Sleep 1300ms

# 5) Confirm tag change — only 'experiment' remains.
Type "gmlcache session report $SESSION"
Sleep 600ms
Enter
Sleep 2200ms

# 6) Swap the spec to a different provider and model.
Type "gmlcache session update $SESSION \\"
Sleep 300ms
Enter
Type "    --client openai --model gpt-4.1-mini --effort medium"
Sleep 600ms
Enter
Sleep 1600ms

# 7) Clear the spec entirely.
Type "gmlcache session clear-spec $SESSION"
Sleep 600ms
Enter
Sleep 1300ms

# 8) Final report — no spec, tag still intact.
Type "gmlcache session report $SESSION"
Sleep 600ms
Enter
Sleep 2500ms
