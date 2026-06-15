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

## Where we are: 0.0.7 (alpha)

The core idea end to end — record a real agentic **CLI** call once, replay it
forever by content checksum — plus read-only discovery of what is installed.

What works (since 0.0.1):

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

Added in 0.0.2:

- `doctor` — reports which configured clients are present and their `--version`,
  advisory only.
- `models` — lists a client's available models by relaying the client's own
  listing command (Cursor today via `--list-models`), or reports a clean "not
  supported"; it never invents or substitutes a catalog. There is no separate
  "effort discovery": Cursor already encodes effort in the model id, and Claude
  and Codex expose effort levels only in documentation, which the cache does not
  scrape.
- `--json` output on both `doctor` and `models`, valid on every path (absent /
  unsupported / listed) so a caller can parse it unconditionally.
- `run --effort` made optional — each client applies its own default when it is
  omitted; effort remains an explicit part of the cassette key.

Added in 0.0.3:

- An optional, opt-in configuration file (INI, zero dependencies) at the standard
  per-user location. `run` reads `mode` / `store` / `timeout` defaults from
  `[defaults]`; an `[executables]` section gives each client a persistent default
  for the `--executable` seam (for installs off `PATH` or pinning a build).
  Precedence is CLI flag > environment variable > config file > built-in default;
  the executables seam has no environment layer.
- `status` — prints the resolved configuration: which file loaded (if any), each
  effective setting with its source, and any configured executables.

Added in 0.0.4:

- Declared input files (`run --input-file PATH`, repeatable, any file type). The
  cache fingerprints each file's content into the key and widens the prime
  directive to grant read access to exactly those paths; the client reads them in
  place, and only the fingerprint is stored. Content, not names, drives the key.
- `docs/client-mapping.md` — a side-by-side reference of how `run` inputs map to
  each client's command line.

Deliberately **not** in 0.0.1: reading the caller's ambient files, API/HTTP
caching, and dependency-aware validity tracking. Those are below.

Added in 0.0.5:

- Allow-path (`run --allow-path PATH`, repeatable): a declared folder the client
  may scan whose contents cannot be fingerprinted. Non-cacheable by default
  (passthrough — runs fresh, stores nothing; offline is an error). Read access via
  the prime directive for all clients, plus Claude's `--add-dir`; Codex/Cursor hard
  mechanisms deferred to adapter hardening.
- Scan-trust (`trust_scan`, config/env, default off): opt in to caching allow-path
  calls when the scanned folders are asserted stable. Caches on the ordinary key
  (the prompt names the folder); the allow-path never enters the key or cassette.

Added in 0.0.6:

- **Write/trust door (bug fix).** Headless clients refused to write their declared
  output in record mode — Claude paused on a write-permission prompt, Codex
  rejected the non-git run folder and defaulted to a read-only sandbox, and
  cursor-agent refused the untrusted workspace — so a file-producing call recorded
  an empty `response.files`. Each adapter now opens a per-client write/trust grant
  for its own isolated run folder (Claude `--permission-mode acceptEdits`; Codex
  `--skip-git-repo-check --sandbox workspace-write -C <run-dir>`; cursor-agent
  `--trust`), on by default and scoped to that folder; reads outside it are
  unchanged. Cursor additionally receives the prime directive via the prompt
  (argv-only, never keyed), since current cursor-agent has no system-prompt flag
  and ignores rule files headlessly. Verified end-to-end against the live CLIs.

Added in 0.0.7:

- **The cache owns its store location (breaking).** The cassette store is set
  only by the config file, defaulting to the per-user data dir
  (`~/.local/share/generic-ml-cache/cassettes`, honoring `XDG_DATA_HOME`) rather
  than a `.gmlcache` folder in the working directory. The `--store` flag, the
  `GMLCACHE_STORE` environment variable, and the `--output-dir` flag are retired:
  a per-call store override forks the cache and defeats reuse, and the cache now
  writes produced files into the directory it was called in, exactly as the client
  would. `gmlcache init` materialises the config file (defaults filled in, never
  overwriting) so the store path is easy to edit; `GMLCACHE_CONFIG` still selects a
  whole alternate config for a deliberate isolated instance.

## Road to 1.0.0 (the rest of the alpha series)

These are the things that must land — and prove themselves stable — before the
version number loses its leading zero. They arrive across `0.0.x` and `0.1.x`
releases, **one feature per release**.

### Design invariants (these constrain every item below)

- **A detached-mode cache, never an interception proxy.** It records and replays
  *headless client subprocess* calls. It does not sit between a client and a
  provider's API; that is a separate, post-1.0.0 idea (below) and explicitly not
  this software's mission.
- **As dumb as possible.** Determinism is the caller's responsibility. The cache
  adds no cleverness to "help" beyond watching declared inputs and reproducing
  what it captured. Rename a file, change a prompt — that is the caller's to
  manage; the cache simply records a different call.
- **Soundness: the key captures everything that changes the client's output.** A
  hit is served only when replay is faithful. Anything the cache cannot
  fingerprint, it must not cache.
- **The cache owns one folder.** It reproduces what was created/modified inside
  its own isolated run folder. It does not track or re-apply changes to files
  outside that folder.

### Immediate next releases

- **`0.0.7` — The cache owns its store; no caller-dictated locations.** The
  cassette store location is set only by the config file (built-in default: the
  per-user data dir, `~/.local/share/generic-ml-cache/cassettes`, honoring
  `XDG_DATA_HOME`). **Retired:** the `--store` flag, the `GMLCACHE_STORE`
  environment variable, and the `--output-dir` flag — the cache writes produced
  files into the directory it was called in, exactly as the client would. **Added:**
  `gmlcache init` to materialise the config file so the store path is editable;
  `GMLCACHE_CONFIG` still selects a whole alternate config (a deliberate isolated
  instance, not a per-call redirect). A per-call store/output override would fork
  the cache into per-caller copies and defeat the one thing a cache is for — reuse.
- **`0.0.8` — Partial / failed-record robustness + clean interruption.** Clear,
  tested behavior when a real call crashes, times out, or is interrupted
  mid-record, so the store is never left with a half-written cassette. Writes are
  already atomic; the surrounding policy needs to be specified and tested.
  **Graceful stop on signal (added requirement):** when the caller sends a
  termination signal — the engine stopping a run — the cache must tear down the
  **client subprocess it spawned** (no orphaned client) and treat the call as an
  interrupted record under the same policy, rather than blocking until the client
  exits on its own. The client runs today under a blocking `subprocess.run`, which
  does not propagate a stop to the child; this needs a killable child (its own
  process group) and a signal handler. *The workflow engine depends on this for its
  cross-app clean stop: the engine signals the cache, the cache owns the teardown.*

### Later `0.0.x` / `0.1.x`

- **`0.0.9` — Store ergonomics + observability.** Cassettes become effectively
  **immutable**, and a separate, **non-load-bearing** access registry (stdlib
  `sqlite3`, so still zero third-party dependencies) records access **events** —
  hit / miss / record / evict — beside the store. The registry never gates a
  lookup or a replay: lose it, corrupt it, or delete it and correctness is
  untouched; it only powers observability and idle-based pruning, and every write
  to it is best-effort. On top of it:
  - **`prune`** — operator-invoked, never automatic: by **idle** (time since last
    access, read from the registry), by **age**, or by **total size**
    (`--max-size`, `--keep N`).
  - **`stats`** — hit rate, hottest/coldest cassettes, eviction history.
  - A documented on-disk layout that callers can rely on.

  Because eviction events remain after the cassette is gone, the registry outlives
  what it describes, so it carries its **own retention/compaction** story rather
  than becoming a new unbounded surface.

- **`0.0.10` — Adapter hardening.** The launch-flag mappings for `claude` /
  `codex` / `cursor-agent` are best-effort today. Before 1.0.0 they need
  verifying against the real CLIs, making configurable where the CLIs differ, and
  degrading gracefully when a flag is unsupported.

- **Analysis — Codex model discovery.** Today `models` reports "not supported" for
  Codex (no scriptable list). `codex debug models` exposes the account-aware model
  catalogue (mirroring Cursor's `--list-models`), but it is an *experimental*
  subcommand. An analysis/design task to decide whether and how the Codex adapter
  should enumerate models through it — degrading gracefully if its shape changes —
  before any implementation. Decide first, then build.

- **`0.1.0` — Documented, versioned cassette schema.** `SCHEMA_VERSION` exists;
  this adds a written schema document, a compatibility policy, and a migration
  path for cassettes written by older versions. It documents the **final** shape —
  including the input-file fingerprint and the scan-trust provenance flag, and
  explicitly **no** deletion field. The minor bump signals the format is now a
  committed contract; it lands after the behavior-shaping items above so it
  describes what is actually true.

- **`0.1.1` — Small, stable public Python API.** The CLI is the primary surface
  today. This exposes a documented library API (recording, lookup, replay,
  inspection, prune/stats) with semantic-versioning guarantees. Done last so it
  reflects final behavior.

When all of the above are done and stable, the project ships **1.0.0**.

## After 1.0.0 (named, deliberately out of scope for now)

These are recorded here so the scope of the alpha stays honest. None is a
commitment.

### v2 — API / HTTP proxy caching

A possible future capability, **explicitly not the core mission** and perhaps
never built. A different mechanism from CLI subprocess caching: intercept HTTP at
the API layer rather than launching a subprocess and diffing a folder. Caching a
provider's own API to save tokens is fundamentally the provider's concern, not
this cache's — so this stays a maybe, recorded only for honesty. If it is ever
built, the aim would be **one cassette format for both CLI and API calls**.

Because a proxy is a long-running network service (unlike the ephemeral CLI
case), it carries a larger security surface. The intended default would be
**local / trusted use only** (bound to localhost); exposing it on a shared
network is *not* the proxy's job — that belongs to a reverse proxy or VPN in
front of it providing TLS and authentication. It could also carry optional
**per-API policy** (e.g. blocking calls to a particular API for compliance/PII
reasons) — meaningful only for the proxy, pointless in the local CLI case where
the caller already chooses exactly which client and model to run.

### Daemon / resident-service features (only meaningful with a long-running process)

The CLI is one-shot, so anything that needs a background loop or shared live
state belongs to a resident service (the proxy above, or a dedicated local-server
mode), never the launcher:

- **Automatic eviction by policy.** The operator-invoked `prune` of 0.0.8 becomes
  a background sweep on a configured interval — idle / age / size **TTL** as app
  configuration rather than a per-call argument — plus an admin "clean now"
  command. The CLI keeps only manual `prune`; an automatic sweep needs a process
  that stays alive.
- **Per-user quotas.** Caps per user (size or count) only have meaning once the
  cache is a multi-tenant service. There is no "user" in the local CLI.

### Packaging (a v2-era thought)

A possible split into a **client-only** release (the content-addressed store,
adapters, CLI) and a **full** release (client **+** a local server providing the
resident-service features above), both sharing the same cassette format.

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
