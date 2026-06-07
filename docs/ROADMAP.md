# Roadmap

This document describes where `generic-ml-cache` is today and where it intends to
go. It is a statement of intent, not a promise. Dates are deliberately absent;
the project moves when the work is done and the tests are green.

The guiding rule for versioning: **the project stays in alpha (`0.x.y`) until the
full v1 feature set is implemented and stable. When every item in the "Road to
1.0.0" section below is done, the version becomes `1.0.0`.**

Version numbers track capability and stability only. Project logistics — renaming
the project, publishing to PyPI, moving repositories — are independent of the
version and can happen at any point.

## Where we are: 0.0.1 (alpha)

The first tagged release. It implements the core idea end to end: record a real
agentic **CLI** call once, replay it forever by content checksum.

What works in 0.0.1:

- The cassette format — one inspectable JSON file per recorded call, with
  `client` / `model` / `effort`, `input_data` (`context`, `prompt`), and a
  `response` (`stdout`, `stderr`, `exit`, captured `files`).
- Container-independent checksums: the same text yields the same checksum whether
  it lived in a standalone file or inside a JSON string. Newlines and tabs are
  significant and never stripped.
- The three modes: `offline` (serve from cache, miss is an error), `cache`
  (hit serves, miss records), and `refresh` (always call, overwrite).
- Isolation as correctness: the client always runs in the cache's own isolated
  folder so created/modified files can be attributed to the run by before/after
  diffing. On replay, captured files are written into the caller's folder.
- The prime directive injected at record time (read/write only within the
  folder, exit to stderr if asked to touch anything outside) — and never stored
  in the cassette.
- Adapters for headless `claude`, `codex`, and `cursor-agent`.
- A cross-platform test suite (Linux / macOS / Windows) with no dependency on a
  real CLI being installed.

Deliberately **not** in 0.0.1: reading the caller's ambient files, API/HTTP
caching, and dependency-aware validity tracking. Those are below.

## Road to 1.0.0 (the rest of the alpha series)

These are the things that must land — and prove themselves stable — before the
version number loses its leading zero. They will arrive across `0.0.x` and
`0.1.x` releases.

The immediate next releases after the first tag:

- **`0.0.2` — Client discovery (`doctor`).** A read-only command that reports
  which configured clients are present and runnable on the current machine
  (presence + version), and — best-effort and **advisory only** — the models and
  effort levels each client itself exposes, by relaying that client's own listing
  mechanism. This makes the cache a *client-abstraction layer*: a caller can ask
  "what is available here?" and "run this exact call" without embedding any
  client-specific knowledge of its own. It is strictly **detection, not
  selection** — discovery never chooses, never restricts, and never gates; a
  model the cache has never heard of still runs, because the run is the validator.

- **`0.0.3` — Configuration.** An optional config file at the standard per-user
  location (the XDG / OS config directory) holding defaults such as the mode and
  the store path. It is discovered only if present, **never auto-written on
  install**, and always overridable, with explicit precedence: CLI flag > environment
  variable > config file > built-in default (the default remains `cache`). A
  `status` command prints the resolved configuration — which file was loaded, if
  any, and the effective settings — so behavior is never a mystery.

- **`0.0.4` — Declared file access (`allow-path`).** A per-execution allowlist of
  paths the client may **read** (for tasks like scanning a source tree),
  translated into each client's own access-restriction mechanism, best-effort
  where a client has none. **Writes** stay confined to and captured from the
  isolated folder, exactly as today. Because the cache cannot know whether the
  contents of those paths changed between runs, a call that declares `allow-path`
  runs **passthrough by default** — it executes the real client and does *not*
  serve or store a cassette — so a scan is always fresh and leaves no stale
  recording behind. Freshness stays the caller's responsibility (force a fresh run
  when inputs change), keeping the cache dumb. Soundly *caching* a file-reading
  call — by folding the declared paths' contents into the key — is the separate
  dependency-aware enhancement below, deliberately not required here. This release
  is the threshold at which the cache can front real file-reading workloads (such
  as scanning a codebase), not only self-contained prompt-to-output calls.

The remaining items, across later `0.0.x` / `0.1.x`:

1. **Adapter hardening.** The launch-flag mappings for `claude` / `codex` /
   `cursor-agent` are currently best-effort and follow one toolchain's
   conventions. Before 1.0.0 they need to be verified against the real CLIs,
   made configurable where the CLIs differ, and covered by adapters that degrade
   gracefully when a flag is unsupported.
2. **A documented, versioned cassette schema.** `SCHEMA_VERSION` exists; 1.0.0
   needs a written schema document, a compatibility policy, and a migration path
   for cassettes written by older versions.
3. **Deletion capture.** v0.0.1 captures created and modified files only.
   Deletions are ignored. 1.0.0 should represent deletions in the cassette so
   replay can faithfully reproduce a run that removed a file.
4. **A small, stable public Python API.** The CLI is the primary surface today.
   1.0.0 should expose a documented library API (recording, lookup, replay,
   inspection) with semantic-versioning guarantees.
5. **Robustness around partial and failed records.** Clear, tested behavior when
   a real call crashes, times out, or is interrupted mid-record, so the store is
   never left with a half-written cassette. (Writes are already atomic; the
   surrounding policy needs to be specified and tested.)
6. **Store ergonomics.** Listing, pruning, and inspecting cassettes from the CLI;
   a documented on-disk layout that callers can rely on.

When all of the above are done and stable, the project ships **1.0.0**.

## After 1.0.0 (named, deliberately out of scope for now)

These are real intentions, recorded here so the scope of the alpha stays honest.

### v2 — API / HTTP proxy caching

The next major capability after `1.0.0`, and a committed direction rather than a
maybe. A different mechanism from CLI subprocess caching: intercept HTTP at the
API layer rather than launching a subprocess and diffing a folder. The aim is
**one cassette format for both CLI and API calls**, so a project's whole model
surface caches in one place.

Because a proxy is a long-running network service (unlike the ephemeral CLI
case), it carries a larger security surface. The intended default is **local /
trusted use only** (bound to localhost). Exposing it on a shared network is
explicitly *not* the proxy's job — that belongs to a reverse proxy or VPN in
front of it providing TLS and authentication. This boundary will be stated
prominently in its docs so the service is never naively exposed.

Because the proxy mediates API access, it could also carry optional **per-API
policy** — e.g. blocking calls to a particular API so they can't be made through
the cache (a compliance/PII control). This has no analogue in the local CLI case,
where the caller already chooses exactly which client and model to run, so such a
gate would be pointless there; it is meaningful only for the proxy.

### Dependency-aware caching (validity tracking)

A cache entry could, in principle, know which external files a call depended on
and invalidate itself when they change. If this is ever built, it must use
**OS-level filesystem tracing** (`strace` on Linux, `fs_usage` on macOS, and the
Windows equivalent) to observe what was actually read — **not** the model's
self-report. Asking the model what it read is best-effort and unsound, and the
cache's whole value rests on being trustworthy.

## How scope decisions get made

See [`../GOVERNANCE.md`](../GOVERNANCE.md). In short: the roadmap is a living
document, anyone may propose a change via an issue, and the maintainers decide
what lands in which version with a bias toward keeping the core small and the
cache "dumb" — determinism is the caller's responsibility, not the cache's.
