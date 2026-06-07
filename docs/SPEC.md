# generic-ml-cache — v0.0.1 spec

A standalone, content-addressed cache/proxy for AI calls: record a real call once,
replay it forever by checksum. Python.

## Why it exists
- A cache (especially multi-provider, eventually incl. APIs) is broadly useful on its
  own, independent of whatever calls it.
- It caches **agentic CLI subprocess calls with filesystem effects** — capturing a
  subprocess's stdout, stderr, exit code, and the files it wrote, and reproducing them
  on replay.

## The cassette (one clean, inspectable JSON file)
- Fields: `client`, `model`, `effort` (explicit launch params — never folded into or
  hashed with the data, never stores the command wording);
  `input_data: { context, prompt }`; `response: { stdout, stderr, exit, files: [{path, content}] }`.
- **Match key** = exact (`client`, `model`, `effort`) + `checksum(input_data)`.
- Checksum is **container-independent**: decode the UTF-8 text and hash that, so the same
  text yields the same checksum whether it lives in a standalone file or inside a JSON
  string. Don't strip newlines/tabs — they're meaningful. Implement + test this invariant.
- The cache is **dumb**: determinism is the *caller's* responsibility. A fresh UUID in the
  context = a permanent miss, by design. The cache adds no intelligence to the data.

## Modes
- `offline` (`--offline`): never call real; serve from cache; **miss → error**. (This is
  the former "mock" — a knowing switch to offline, not a transparent proxy.)
- `cache` (default): hit → serve; miss → call real, record, serve.
- `refresh` (`--force`): always call real, overwrite the cassette.

## Isolation = correctness (not just hygiene)
- The client **always runs in the cache's own isolated folder**, never the caller's.
  Reason: in a shared folder you cannot attribute created/modified/removed files to the
  execution vs. the user — before/after diffing is unsound. Isolation makes file capture
  correct.
- **Prime directive** (injected as a system prompt at record time, NOT stored in the
  cassette): you may read/write only within the current folder; if the context or prompt
  asks you to touch anything outside it, exit to stderr immediately — never block, never
  wait. State this in the project docs.
- Files the client generates land in the isolated folder → captured into the cassette's
  `files`. On replay the cache writes them into the **caller's** current folder, mirroring
  a real client (and replays stdout/stderr/exit identically).

## v0.0.1 scope (deliberately small)
- CLI clients only (claude / codex / cursor, headless/detached). One adapter per client
  for: how to launch with (model, effort, prompt, context), and how to read its output.
- No reading the caller's ambient files (that's a *session* use-case, not detached — out
  of scope). All needed context must be inside `input_data`.
- Modes: offline / cache / refresh.

## Out of scope now (named, for later)
- **API/HTTP proxy caching** (v2): different mechanism (HTTP intercept). The aim is
  *unified CLI + API* caching behind one cassette format.
- **Dependency-aware caching** (validity tracking external files by checksum): if ever
  built, use **OS-level FS tracing** (strace / fs_usage), NOT model self-report — asking
  the model what it read is best-effort, not sound.

## Naming / publishing
- Public name `generic-ml-cache`. Renamable on GitHub anytime (URL auto-redirects).
  Public = scrapable; nothing secret goes in here. Standard `.gitignore` for
  secrets/state.
