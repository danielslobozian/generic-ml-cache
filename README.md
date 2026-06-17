# generic-ml-cache

**A content-addressed cache for expensive, non-deterministic AI calls.** Record a
real call once, replay it forever by checksum — turning a slow, costly, variable
invocation into a cheap, reproducible one. It does one thing well.

Today it caches **agentic CLI calls** (headless `claude` / `codex` / `cursor`,
including the files they write). The roadmap extends the same cassette format to
**API / HTTP calls**, so a project's whole model surface — subprocess *and* API —
can be cached behind one format (see [`docs/ROADMAP.md`](docs/ROADMAP.md)).

> ⚠️ **Status: alpha.** The format and CLI are still settling and may
> change between 0.0.x releases. It is usable today for caching headless
> `claude` / `codex` / `cursor` calls; it is not yet API-stable. The version
> reaches **1.0.0** only when the full v1 feature set (see
> [`docs/ROADMAP.md`](docs/ROADMAP.md)) is in.

## Why it exists

Recording an HTTP fixture for a test is routine; recording an *agentic* call — one
that thinks, writes files, and prints output — is not. This tool makes that just as
ordinary. It caches **agentic CLI subprocess calls with filesystem effects** (a
`claude -p ...` run that edits files) today, and grows toward caching **API / HTTP**
calls too — one cassette format for *both* CLI and API, so a project's whole model
surface caches in one place.

What it buys you:

- **Tests & CI** that exercise AI-driven workflows run offline, deterministically,
  and for free, against recorded fixtures.
- **Iterating** on the code *around* a model call without paying for (or waiting
  on) the model every run.
- **Reproducibility**: a cassette is a single, inspectable JSON file you can read,
  diff, and commit.

## How it works

Every call is keyed by an exact match of **`(client, model, effort)`** plus a
**container-independent checksum** of the input (`context` + `prompt`). The same
text always produces the same key, whether that text lived in a file or inside a
JSON string.

A real call is recorded by running the client inside the cache's **own isolated
folder** (never yours) so that created/modified files can be attributed to the
run rather than to whatever you already had on disk. The result — stdout, stderr,
exit code, and produced files — is written to a **cassette**. On replay, the
cache reproduces stdout/stderr/exit exactly and writes the produced files into
your current folder, mirroring a real client.

```
                 ┌─────────── match key ───────────┐
request ──▶ (client, model, effort) + checksum(context, prompt)
                                  │
                 ┌────────────────┴─────────────────┐
              hit │                                  │ miss
                  ▼                                  ▼
        replay cassette                 run client in isolated folder,
   (stdout/stderr/exit/files)           capture response → write cassette
```

### The cassette

```jsonc
{
  "schema_version": 1,
  "client": "claude",
  "model": "claude-sonnet-4",
  "effort": "high",
  "input_checksum": "…",          // recomputed on match; shown for inspection
  "input_data":  { "context": "…", "prompt": "…" },
  "response": {
    "stdout": "…", "stderr": "…", "exit": 0,
    "files": [ { "path": "out/result.txt", "content": "…", "encoding": "utf-8" } ]
  }
}
```

The launch params (`client`, `model`, `effort`) are explicit fields — they are
part of the *key* but are **never** folded into the data checksum, and the actual
command wording is never stored. The cache is deliberately **dumb**: making the
input deterministic (no stray UUIDs, timestamps, or paths in the context) is the
*caller's* job. A fresh UUID in the context is, correctly, a permanent miss.

## Install

Install from source (works today):

```bash
pip install git+https://github.com/danielslobozian/generic-ml-cache.git
```

A PyPI release (`pip install generic-ml-cache`) is planned but not yet available.

Requires Python ≥ 3.9. Pure standard library — no runtime dependencies.

## Usage

```bash
# First run: cache miss → calls real `claude`, records a cassette, replays it.
gmlcache run \
  --client claude --model claude-sonnet-4 --effort high \
  --context-file context.md --prompt-file task.md

# Same inputs again: cache hit → instant, free, identical output.
gmlcache run --client claude --model claude-sonnet-4 --effort high \
  --context-file context.md --prompt-file task.md
```

### Modes

| Mode | Flag | Behavior |
| --- | --- | --- |
| `cache` (default) | — | hit → serve; miss → call real, record, serve |
| `offline` | `--offline` | serve from cache only; **a miss is an error** |
| `refresh` | `--force` | always call real, overwrite the cassette |

Offline mode is the "known fixtures only" mode for CI: it never reaches the
network and fails loudly if a cassette is missing.

### Other commands

```bash
gmlcache inspect ./cassettes/<key>.json   # human-readable summary of a cassette
gmlcache --version
```

See [`docs/usage.md`](docs/usage.md) for the full reference and
[`docs/design.md`](docs/design.md) for the architecture.

## Hopes & non-goals

**Hopes.** That recording an agentic CLI call becomes as ordinary as recording an
HTTP fixture — a thing you reach for without thinking, that makes AI-driven code
testable and cheap to iterate on. Eventually: one cache that covers **both** CLI
subprocesses and HTTP/API calls, so a workflow's whole model surface can be
captured in one place.

**Non-goals.** This is not an orchestrator or a prompt framework. It adds no
intelligence to your data, makes no decisions about *what*
to call, and will never try to be smart about determinism on your behalf.

## Who can use it

Everyone. Released under the **Apache License 2.0** — free for personal,
academic, and commercial use, including in closed-source products, with a patent
grant. See [`LICENSE`](LICENSE). Contributions are welcome under the same license;
see [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Project docs

- [`docs/ROADMAP.md`](docs/ROADMAP.md) — the path from 0.0.1 (alpha) to 1.0.0 and beyond
- [`docs/SPEC.md`](docs/SPEC.md) — the v0.0.1 specification
- [`docs/design.md`](docs/design.md) — architecture and the reasoning behind it
- [`docs/usage.md`](docs/usage.md) — full CLI and library reference
- [`docs/storage.md`](docs/storage.md) — the on-disk store layout
- [`CHANGELOG.md`](CHANGELOG.md) — release history
- [`SECURITY.md`](SECURITY.md) — how to report a vulnerability
- [`GOVERNANCE.md`](GOVERNANCE.md) — how decisions get made

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
