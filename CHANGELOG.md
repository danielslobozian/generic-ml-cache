# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the version is `0.x.y` the project is in **alpha** and anything may change
between releases; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the path to `1.0.0`.

## [Unreleased]

### Added

- `gmlcache doctor`: a read-only command that reports which configured clients
  are present on the current machine and their `--version` output. Advisory only
  — discovery never chooses a client, never restricts a model, and never gates a
  run; a client it cannot find is reported as missing rather than as an error.

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

[Unreleased]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/danielslobozian/generic-ml-cache/releases/tag/v0.0.1
