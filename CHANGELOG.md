# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the version is `0.x.y` the project is in **alpha** and anything may change
between releases; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the path to `1.0.0`.

## [0.0.9] - 2026-06-17

### Added

- **Opt-in size eviction (`max_size`).** Off by default — the cache keeps every
  cassette forever. Set `max_size` (config `[defaults]` or `GMLCACHE_MAX_SIZE`,
  e.g. `5GB` / `500MB` / a byte count) and the cache evicts the
  least-recently-used cassettes to make room as it records new ones (LRU from the
  access registry, falling back to file age). It is a **soft cap**: a fresh result
  is always stored, even if that briefly overshoots, rather than discarding a call
  you just paid for; eviction is best-effort and never blocks or fails a save, and
  each eviction logs an `evict` event. Time-based ("not used in N days") eviction
  is deferred to daemon mode (see ROADMAP). `status` now shows the resolved cap.

- **`stats` command.** Reports how many cassettes are stored, their total size
  split by client and model, and the access-event counts (hit / miss / record)
  from the registry — in a human table or `--json`. It is the diagnostic that
  lets a user watch the cache's footprint (e.g. on a daily dashboard) and decide
  whether to turn on an eviction policy, rather than the cache imposing one.

- **Access registry (observability).** A small SQLite log (`registry.sqlite3` in
  the store dir, stdlib `sqlite3`, no extra dependency) records cache access
  events — hit / miss / record (and eviction, once `prune` lands) — for the coming
  `stats` and `prune` to read. It is **non-load-bearing by construction**: every
  registry operation swallows its own errors, so a missing, locked, unwritable, or
  corrupt database never affects whether or how the cache resolves a call. It
  records access only — no checksums, no integrity claims (a checksum kept beside
  the data it guards protects nothing a determined editor couldn't also rewrite).

- **Cassettes are write-once and immutable.** A cassette is built fully in memory
  from the client's response and the keep-or-discard decision is made before
  anything is written, so the file is materialized in one shot and never reopened
  for writing. Once written it is marked **read-only** on disk (cross-platform, on
  the cache's own files only — no effect on anything else on the system). A cache
  hit is a pure read and never writes back into the cassette: all mutable
  bookkeeping will live in the side access registry, keeping recordings pure.
  Read-only is a soft deterrent (the owner can clear it, root ignores mode bits);
  firm tamper-detection is planned via a registry-held checksum. `refresh` clears
  the flag before atomically replacing, so re-recording still works everywhere.

## [0.0.8] - 2026-06-17

### Added

- **Partial-record robustness — a half-written cassette can never be left behind.**
  Cassette writes now use a per-process unique temp file in the store directory,
  cleaned up on any failure (write, replace, or signal), so a crash mid-write
  leaves neither a half-written cassette nor a stray temp file; the cassette is
  rendered before anything touches disk, so a serialization fault writes nothing.
  A real call that exceeds `--timeout` is killed and unwinds before any write
  (nothing recorded); the CLI now maps that to exit code **124** (the `timeout(1)`
  convention) with a clear message instead of an uncaught error, and documents
  exit **130** for a caller-signalled stop.

- **Failed client calls are not cached by default.** A real call that exits
  non-zero is no longer stored: the caller still receives the real failed
  response, but nothing is written to the store, so the next identical call runs
  fresh instead of replaying a transient failure (a bad model id, an auth hiccup,
  a rate limit) forever. The new `gmlcache run --record-on-error` flag (and
  `resolve(..., record_on_error=True)`) opts into storing failures as well, for
  the cases where a deterministic failure is itself the result worth replaying.
  A `refresh` whose fresh call fails leaves any existing successful cassette
  untouched rather than overwriting it. Naming follows VCR's `record_on_error`.

- **Graceful stop on signal.** A real client call now runs in its own process
  group/session and is supervised: when the caller (the workflow engine) sends a
  termination signal — `SIGINT`/`SIGTERM` — the whole group is torn down (no
  orphaned client) and the run raises `RunInterrupted`, so no cassette is written
  (an interrupted call is not a result). `gmlcache run` maps it to exit code `130`,
  distinct from a miss (3) or an error (4). The blocking `subprocess.run` is
  replaced by a supervised `Popen`; timeout behavior is unchanged (kill the group,
  re-raise). Signal handlers are installed only on the main thread; off it the run
  still tears down on timeout. POSIX uses `killpg`; Windows terminates the child.

### Changed

- **Roadmap — `0.0.8` gains a graceful-stop-on-signal requirement.** Partial/failed
  -record robustness is extended: on a termination signal from the caller (the
  workflow engine stopping a run) the cache must tear down the client subprocess it
  spawned and treat the call as an interrupted record, rather than blocking until
  the client exits. Documents the cross-app contract the workflow engine's clean
  stop depends on (the engine signals; the cache owns the teardown). Documentation
  only; no runtime change.

## [0.0.7] - 2026-06-13

### Changed

- **The cache owns its store location; it is no longer a caller-dictated knob.**
  The cassette store is set only by the config file, falling back to a built-in
  per-user default at `$XDG_DATA_HOME/generic-ml-cache/cassettes` (i.e.
  `~/.local/share/generic-ml-cache/cassettes`; `%LOCALAPPDATA%\generic-ml-cache\cassettes`
  on Windows) instead of the old `.gmlcache` folder in the current directory. A
  per-call store override would fork the cache into per-caller copies and defeat
  reuse, so it is gone; to run a fully isolated cache, point `GMLCACHE_CONFIG` at
  a different whole config file.
- **The cache writes produced files into the directory it was called in**, exactly
  as the real client would, with no override flag — to put outputs elsewhere, run
  the cache there.

### Added

- **`gmlcache init`** — creates the config file in its default location (if absent)
  with the defaults filled in, so the store path is easy to find and edit. It
  never overwrites an existing file, and the cache still works with no config at
  all (built-in defaults).

### Removed

- **`--store` flag, `GMLCACHE_STORE` environment variable, and `--output-dir`
  flag** on `gmlcache run` (breaking). The store location lives in the config; the
  output location is always the working directory. `mode`/`timeout` keep their
  flag and environment layers; only the store and output *locations* lose theirs.

## [0.0.6] - 2026-06-13

### Fixed

- **Write/trust door — headless clients could not write their declared output
  file.** On the first real record-mode use, a file-producing call recorded an
  empty `response.files`: Claude paused on a write-permission prompt and only
  narrated the file, Codex rejected the non-git run folder (`Not inside a trusted
  directory`) and otherwise defaulted to a read-only sandbox, and cursor-agent
  refused the untrusted workspace (`Workspace Trust Required`). The before/after
  diff therefore captured nothing. Each adapter now opens a per-client write/trust
  grant for its own isolated run folder — **on by default** and scoped to that
  folder, so reads *outside* it are unchanged: Claude `--permission-mode
  acceptEdits`, Codex `--skip-git-repo-check --sandbox workspace-write -C
  <run-dir>`, cursor-agent `--trust`. Mirrors the existing `read_access_argv`
  seam via a new `write_access_argv(run_dir)` on the adapter base. Flags verified
  against the live CLIs; `docs/client-mapping.md` updated and the row marked
  verified.
- **cursor-agent has no system-prompt channel in headless mode.** It exposes no
  `--system-prompt` flag (removed upstream) and ignores workspace rule files
  (`.cursor/rules`, `.cursorrules`, `AGENTS.md`) under `--print` — both verified
  against the live CLI. The Cursor adapter now prepends the prime directive to the
  prompt argument itself. This is argv-only: the directive never enters
  `Request.input_data`, so the cache key is unchanged and cursor keys identically
  to claude and codex. Surfaced by the end-to-end record regression through
  gmlcache, which the unit tests and direct-client isolation had missed.

## [0.0.5] - 2026-06-11

### Added

- Allow-path: `run --allow-path PATH` (repeatable) declares a folder the client may
  scan/read whose contents the cache cannot fingerprint. Because what was read (and
  whether it changed) is unknowable, such a call is **non-cacheable by default** —
  it runs fresh and stores nothing (passthrough), and in offline mode it is a clear
  error. The folder is granted read access via the prime directive for every client
  and, on Claude, a real `--add-dir <folder>`; writes stay confined to and captured
  from the isolated run folder. (Codex/Cursor hard read mechanisms are deferred to
  adapter hardening.)
- Scan-trust: an opt-in `trust_scan` setting (`[defaults]` in the config file, or
  `GMLCACHE_TRUST_SCAN`; default `false`; no per-call flag) that lets allow-path
  calls be cached anyway when you assert the scanned folders are stable. They cache
  on the ordinary key — the prompt already names the folder — and the allow-path
  never enters the key or the cassette. `status` shows the effective value; use
  `--force` to re-record.

## [0.0.4] - 2026-06-11

### Added

- Declared input files: `run --input-file PATH` (repeatable, any file type). The
  cache fingerprints each file's content into the cache key — so a content change
  is a different call — and opens the read-door for exactly those paths (the prime
  directive is widened to permit reading them, nothing else outside the run
  folder). The client reads the files itself, in place; the cache stores only the
  fingerprint, never the content. The key watches content, not names: a rename
  with identical content is still a hit, order is irrelevant, and identical-content
  files collapse to one entry. `inspect` lists input-file fingerprints.
- `docs/client-mapping.md`: a side-by-side reference of how each `run` input maps
  to the `claude` / `codex` / `cursor-agent` command lines, plus the discovery
  mapping and the cache-only flags that never reach a client.

## [0.0.3] - 2026-06-08

### Added

- Optional configuration file (INI, zero dependencies). `run` reads its defaults
  — `mode`, `store`, `timeout` — from `[defaults]` in a per-user config file when
  one exists (`$XDG_CONFIG_HOME`/`~/.config` on Linux/macOS, `%APPDATA%` on
  Windows; override with `GMLCACHE_CONFIG`). The file is opt-in and never written
  automatically. Precedence is CLI flag > environment variable
  (`GMLCACHE_MODE` / `GMLCACHE_STORE` / `GMLCACHE_TIMEOUT`) > config file >
  built-in default.
- Optional `[executables]` section in the same config file, mapping a client name
  to the path (or bare command) used to launch it — a persistent default for the
  per-call `--executable` seam, for installs not on `PATH` or for pinning one of
  several builds. Used by `run`, `doctor`, and `models`; it only changes *where* a
  client is launched, never *which* client or model runs. Precedence per client is
  `--executable` flag > `[executables]` config > the adapter's own `PATH` lookup
  (no environment layer). Unknown client keys are kept rather than rejected, and a
  path is not validated until that client is actually launched.
- `gmlcache status` (with `--json`): prints which config file was loaded, if any,
  the effective settings with the source of each value (flag / env / config /
  default), and any configured client executables.

## [0.0.2] - 2026-06-07

### Changed

- `run --effort` is now optional. When omitted, each client applies its own
  default instead of receiving an empty value: Claude drops the `--effort` flag,
  Codex leaves `model_reasoning_effort` unset, and Cursor uses the model id as
  given (so a full id from `models` that already encodes effort is passed through
  unchanged). Effort remains an explicit part of the cassette match key, and an
  empty effort is a distinct key value.

### Added

- `gmlcache doctor`: a read-only command that reports which configured clients
  are present on the current machine and their `--version` output. Advisory only
  — discovery never chooses a client, never restricts a model, and never gates a
  run; a client it cannot find is reported as missing rather than as an error.
- `gmlcache models [client]`: lists the models a client reports it can use, by
  relaying the client's own listing command and structuring the output — the
  cache never hardcodes or substitutes a catalog, so the result reflects what the
  authenticated client can actually reach. Reports a clean "not supported" when a
  client has no listing command. Of the built-in adapters, Cursor
  (`cursor-agent --list-models`) is supported today; Claude and Codex report
  "not supported" via a ready relay seam (`models_argv` / `parse_model_list`).
- `--json` output for `doctor` and `models`, valid on every path (absent /
  unsupported / listed) so callers can parse it unconditionally.

## [0.0.1] - 2026-06-07

The first alpha release. Records a real agentic **CLI** call once and replays it
forever by content checksum.

### Added

- The cassette format: one inspectable JSON file per recorded call, holding
  `client` / `model` / `effort`, `input_data` (`context`, `prompt`), and the
  `response` (`stdout`, `stderr`, `exit`, and captured `files`).
- Container-independent checksums: identical text yields an identical checksum
  whether it came from a file or a JSON string. Newlines and tabs are significant.
- Three modes — `offline` (replay only; miss is an error), `cache` (hit replays,
  miss records), and `refresh` (always call and overwrite).
- Isolation as correctness: the client always runs in the cache's own private
  folder so created and modified files can be attributed to the run by
  before/after diffing. Replayed files are written into the caller's folder.
- The prime directive, injected as a system prompt at record time and never
  stored in the cassette: the client may read and write only within its folder
  and must exit to stderr if asked to touch anything outside it.
- Adapters for headless `claude`, `codex`, and `cursor-agent`.
- The `gmlcache` command line with `run` and `inspect` subcommands.
- A cross-platform test suite (Linux / macOS / Windows) that requires no real
  CLI to be installed.
- Apache-2.0 license and full open-source project documentation.

[Unreleased]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.5...HEAD
[0.0.5]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/danielslobozian/generic-ml-cache/releases/tag/v0.0.1
