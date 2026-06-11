# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the version is `0.x.y` the project is in **alpha** and anything may change
between releases; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the path to `1.0.0`.

## [Unreleased]

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
