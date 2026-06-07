# Design

This document explains how `generic-ml-cache` is built and, more importantly,
*why* it is built that way. The what-and-how of using it lives in
[`usage.md`](usage.md); the formal contract lives in [`SPEC.md`](SPEC.md).

## The one-sentence model

Record a real agentic CLI call once into an inspectable JSON "cassette", then
replay it forever by matching on the exact launch parameters plus a
container-independent checksum of the input.

## What it captures

Caching an agentic **CLI** call — one that spawns a subprocess, reasons over a
prompt, and writes files to disk — means capturing more than a return value. It
requires capturing the subprocess's stdout, stderr, exit code, **and** its
filesystem side effects, then reproducing all of it on replay. That is what this
tool does, and it is why the cache is a standalone concern, independent of whatever
calls it.

## Core components

The package is small and each module has one job.

- **`checksum.py`** — turns `input_data` into a stable, container-independent
  digest. This is the heart of correctness (see below).
- **`cassette.py`** — the data model: `Cassette`, `Response`, `CapturedFile`, and
  the `match_key`. Knows how to serialize to and from one tidy JSON file.
- **`store.py`** — a directory of cassettes keyed by match key. Lookups and
  atomic saves. Nothing clever.
- **`adapters/`** — one adapter per CLI client. An adapter knows how to turn
  `(model, effort, prompt, context, system prompt)` into an argv and stdin for
  that specific tool, and where it expects to find the executable.
- **`isolation.py`** — runs the real client inside a private temp folder, snapshots
  the folder before and after, and attributes new/changed files to the run.
- **`prime_directive.py`** — the system prompt injected at record time that keeps
  the client inside its sandbox.
- **`cache.py`** — the three-mode state machine (`offline` / `cache` / `refresh`)
  that ties lookup, real execution, recording, and replay together.
- **`cli.py`** — the `gmlcache` command-line surface.

## The decisions that matter

### Container independence is the whole game

The same text must produce the same checksum whether it arrived as a file or as a
string inside JSON. So the checksum decodes UTF-8 bytes to text and hashes the
text, with explicit field framing so that moving a byte from the end of one field
to the start of the next cannot collide. Newlines and tabs are *content* and are
never normalized away. If this invariant broke, two identical inputs could miss
each other, or two different inputs could collide — either way the cache would be
untrustworthy. It is the single most heavily tested behavior in the project.

### The cache is dumb on purpose

The cache adds **no** intelligence to the data. A fresh UUID in the context is a
permanent miss, by design. Determinism is the caller's responsibility. This keeps
the mental model honest: a hit means "byte-for-byte the same question, asked the
same way" and nothing fuzzier. Anything smarter (semantic matching, normalization)
would make hits unpredictable and the tool untrustworthy.

### Match key = explicit params + input checksum, never the wording

The match key is the exact `(client, model, effort)` tuple plus the checksum of
`input_data`. The *command wording* — the actual flags used to launch the tool —
is deliberately **not** part of the key and **not** stored. Two callers who phrase
the launch differently but ask the same model the same question with the same
effort should hit the same cassette.

### Isolation is correctness, not hygiene

The client always runs in the cache's own private folder, never the caller's. The
reason is not tidiness — it is that in a shared folder you cannot soundly attribute
a created or modified file to the run versus the user's pre-existing files. A
before/after diff is only trustworthy when the folder started empty and belongs to
the run. Isolation is what makes file capture correct.

### The prime directive is injected, never stored

At record time the client receives a system prompt instructing it to read and
write only within its folder, and to exit to stderr immediately (never block,
never wait) if the task asks it to touch anything outside. That directive shapes
the recorded behavior but is **not** persisted in the cassette — the cassette
records what the client *did*, not the instructions it was given. The directive is
injected ahead of any caller-supplied system prompt so it cannot be overridden.

### The executable seam

Adapters resolve their executable through one chokepoint: an explicit path is used
verbatim (and errors if missing), while a bare name is looked up on `PATH`. This
is what lets the test suite substitute a fake client and exercise every cache
mechanism on any OS without a real `claude` / `codex` / `cursor-agent` installed.

### Atomic, diff-friendly storage

Cassettes are written to a temp file and then atomically moved into place, so a
crash mid-write never corrupts the store. JSON is emitted with sorted keys and
stable indentation so cassettes diff cleanly in version control and stay readable
by humans.

## Replay fidelity

In quiet mode, replay reproduces the recorded stdout and stderr byte-for-byte,
exits with the recorded code, and writes the captured files into the caller's
current directory — refusing any path that would escape it. Verbose mode adds
`gmlc:` diagnostics on stderr, which by definition breaks byte-exact fidelity; it
exists for debugging, not for piping.

## Testing strategy

The suite never depends on a real CLI. A deterministic fake client, driven by
directives embedded in its prompt, stands in for a real agent and lets the tests
assert on checksums, mode transitions, file capture, isolation, prime-directive
compliance, and byte-exact replay — identically on Linux, macOS, and Windows.
Paths are stored POSIX-style so cassettes are portable across operating systems.
