# gmlcache demo — API adapters: call Anthropic, OpenAI, and Gemini directly.
# The same prompt is sent to all three providers. Repeating it is an instant cache hit.
#
# Render:
#   ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=... \
#   vhs docs/api.tape  ->  docs/images/gmlcache-api.gif
#
# Requires: vhs, gmlcache with API adapter support, and one valid key per provider.
# A cold isolated store is used (XDG_DATA_HOME is reset in the hidden section).

Output docs/images/gmlcache-api.gif

Require gmlcache

Set Shell bash
Set FontSize 24
Set Width 1900
Set Height 1400
Set Padding 40
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 55ms

Hide
Type "export PS1='\[\e[38;5;43m\]gmlcache ❯ \[\e[0m\]'"  Enter
Type "export TIMEFORMAT='   ⏱  %Rs'"  Enter
Type "rm -rf /tmp/gmlcache-api-demo && export XDG_DATA_HOME=/tmp/gmlcache-api-demo"  Enter
Type "clear"  Enter
Show
Sleep 600ms

# Anthropic — first call: real REST call, takes a moment.
Type "time gmlcache run --client anthropic --model claude-haiku-4-5-20251001 --prompt 'What is a content-addressed cache?'"
Sleep 400ms
Enter
Sleep 7s

# Same prompt again — byte-identical instant replay from the cache.
Type "time gmlcache run --client anthropic --model claude-haiku-4-5-20251001 --prompt 'What is a content-addressed cache?'"
Sleep 400ms
Enter
Sleep 2800ms

# OpenAI — same prompt, different provider, real call.
Type "time gmlcache run --client openai --model gpt-4.1-mini --prompt 'What is a content-addressed cache?'"
Sleep 400ms
Enter
Sleep 9s

# Gemini — third provider.
Type "time gmlcache run --client gemini --model gemini-2.0-flash --prompt 'What is a content-addressed cache?'"
Sleep 400ms
Enter
Sleep 9s

# Show what the store holds — 3 executions, 1 cached hit, three providers.
Type "gmlcache stats"
Sleep 400ms
Enter
Sleep 3s
