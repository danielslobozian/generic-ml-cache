# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the version is `0.x.y` the project is in **alpha** and anything may change
between releases; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the path to `1.0.0`.

Since `0.2.0` the project is a **monorepo of lockstep-versioned packages** — the
hexagonal kernel [`generic-ml-cache-core`](packages/core), its concrete adapters
[`generic-ml-cache-adapters`](packages/adapters) (split out in 0.28.0), the CLI
[`generic-ml-cache-cli`](packages/cli), and (since 0.13.0) the optional daemon
[`generic-ml-cache-daemon`](packages/daemon). All share the version below, and this file
is the single changelog for all of them; entries note which package(s) a change touches.

## [Unreleased]

## [0.28.0] - 2026-06-29

The **hexagonal split**: every concrete adapter leaves `core` for a new fourth package,
`generic-ml-cache-adapters`, leaving `core` a pure kernel of domain model, use cases, and
port contracts. Includes the architecture-analysis remediation that hardened the split.

### Added

- **New package `generic-ml-cache-adapters`** (`pip install generic-ml-cache-adapters`):
  every concrete outbound port implementation that previously lived in `core` — the
  SQLite execution repository + schema migrations, filesystem blob store, AES-GCM cipher
  and encryption helpers, all six ML client/API adapters (claude, codex, cursor-agent,
  anthropic, openai, gemini), system clock, filesystem file fingerprint, journal metrics,
  HTTP gateway forward adapter, and the diagnostics adapters. The `encryption` extra
  (`cryptography`) moves here.
- **`AdapterCatalogPort` / `AdapterResolverPort`** (core): the injected adapter-discovery
  contract. `AdapterDescriptor` carries each adapter's boundary, supported execution
  modes, and capabilities; the composition root builds the catalog and injects it.
- **Architecture guards**: `py.typed` for adapters; import-linter contracts for
  `domain ↛ port`, `port ↛ usecase`, and package isolation (`adapters ↛ drivers`,
  `daemon ↛ cli`, `cli ↛ daemon` except the lazy launcher); a core purity unit guard
  (no entry-point scanning, no raw filesystem/subprocess/socket I/O); branch coverage
  across all packages; and the `C901` complexity gate extended to core and adapters.

### Changed

- **Core is now a pure hexagonal kernel** (core): domain model, use cases, and port
  contracts only. Adapter discovery (entry-point scanning) moved out of `core` entirely,
  behind `AdapterCatalogPort` — `core` no longer scans Python packaging metadata.
- **Client adapters are pure translators** (core, adapters): managed execution — the
  isolated workspace lifecycle and artifact capture — is now a `core` use case; each CLI
  adapter composes a shared `CliRuntime` and supplies only its own translation hooks.
- **Daemon routes by client name** (daemon): `/run` and `/jobs` select the adapter for
  the requested client instead of a single hardcoded one, and enforce the configured
  whitelist (HTTP 400 for an unknown or excluded client).
- Cross-package version pins tightened from `>=` to `==0.28.*` so a fresh install can
  never mix incompatible package versions.

### Removed

- **Breaking (adapter authors and embedders)**: `ClientAdapter`, the `@adapter`
  decorator, and the `register` / `get_adapter` registry API are removed from `core`.
  Third-party adapters now declare themselves via the `gmlcache.adapters` entry-point
  group plus a `descriptor()` classmethod; the `register` / `get_adapter` helpers live in
  `generic-ml-cache-adapters`. The vestigial `generic_ml_cache_core.adapter` package and
  the `generic_ml_cache_core.stream` file-I/O class are gone (the latter moved to
  `generic_ml_cache_adapters.stream`).

### Fixed

- **Daemon multi-client correctness** (daemon): a request for a non-default client
  previously dispatched to the hardcoded runner; it now runs the requested client.
- **`httpx2>=2.0` dependency typo** (daemon): corrected to `httpx` in the dev extras.

## [0.27.0] - 2026-06-28

### Fixed

- **`common` pip RECORD collision** (cli, daemon): renamed the shared internal
  folder from the top-level `generic_ml_cache_common` namespace to
  `generic_ml_cache_cli._common` and `generic_ml_cache_daemon._common`
  respectively. Both wheels previously shipped a `generic_ml_cache_common`
  top-level package; pip's RECORD entries collided, so uninstalling either
  package silently removed the other's shared code.
- **Daemon `__version__` stale** (daemon): `__version__` was hardcoded as
  `"0.15.0"`. Replaced with `importlib.metadata.version("generic-ml-cache-daemon")`
  to match the pattern used by core and CLI.
- **Daemon wheel missing license files** (daemon): `LICENSE` and `NOTICE`
  were absent from the built wheel. Added symlinks into the package tree and
  registered them via `license-files` in `pyproject.toml`.
- **Daemon wheel missing README** (daemon): `readme = "README.md"` was
  absent from `pyproject.toml`, leaving the PyPI page blank.
- **CLI README API example wrong** (cli): `build_use_cases` call used a
  wrong keyword argument and incorrect method name. Corrected to match the
  actual public API.
- **Daemon README version label** (daemon): removed the stale `(0.13.0)`
  label from the gateway limitations note.

### Added

- **CI: pyright type-checking job** (ci): new `typecheck` job runs `pyright`
  in basic mode on Python 3.13 across all three packages on every push and PR.
- **CI: import-linter architecture contracts job** (ci): new `import-contracts`
  job runs `lint-imports` to enforce the five hexagonal-architecture contracts
  on every push and PR.
- **CI: coverage floors** (core, cli, daemon): pytest addopts now include
  `--cov` and `--cov-fail-under` (90% core, 80% cli, 80% daemon); the gate
  is applied in every test run including the matrix and Sonar workflows.
- **CI: release artifact verification** (ci): new `verify` job between `build`
  and `publish` runs `twine check` on every wheel/sdist and smoke-installs all
  three packages from the built artifacts before any upload.
- **Exit code reference and stability tests** (cli, docs): `docs/reference/cli.md`
  now contains an authoritative exit code table (0/1/2/3/4/124/130) declared
  stable under the compatibility policy. Eleven regression tests in
  `packages/cli/tests/test_exit_codes.py` guard every documented code.
- **Public API stability contract** (core): `generic_ml_cache_core/__init__.py`
  docstring now explicitly states the SemVer guarantees for the `__all__` surface
  — what patch, minor, and major releases may and may not change.

### Changed

- **Docs: two-package wording removed** (docs): `README.md`, `docs/README.md`,
  `SECURITY.md`, and `CONTRIBUTING.md` updated from two-package to three-package
  descriptions; removed "early, alpha software" framing from `CONTRIBUTING.md`.
- **`docs/reference/cli.md` disclaimer** (docs): replaced the "exact syntax may
  differ" hedge with an authoritative statement; the reference is now the
  normative command surface.
- **pytest-timeout added** (core, daemon): `pytest-timeout` added to dev
  dependencies; `timeout = 60` set in pytest options for both packages.

## [0.26.0] - 2026-06-28

### Added

- **`gmlcache config validate`** (cli): parses and validates the config file
  without executing anything; safe for CI. Collects all errors and warnings
  instead of raising on the first issue. Errors: invalid enum values
  (`mode`, `persist`, `log_level`), bad type conversions (`timeout`,
  `max_size`, `max_age`, `trust_scan`), unparseable file. Warnings: unknown
  keys, unknown sections, `version` key mismatch. Exits 0 when clean or
  warnings-only; exits 4 on any error. `--json` emits a structured
  `{config_path, present, valid, issues[]}` payload.
- **`gmlcache config show`** (cli): displays the fully resolved configuration
  — every key, its current value, and the source that set it
  (`default` / `file` / `env`). `--resolved` flag accepted for
  discoverability. `--json` emits structured output including executables.
  Distinct from `gmlcache status`, which shows runtime and store state.
- **`version` key** (cli): optional `[defaults]` key `version = 1` in the
  config file declares the config schema version. The current schema version
  is `1`. A mismatch produces a warning from `config validate`. The value is
  read into `FileConfig.version` by `load()` for future use.
- **Complete configuration reference** (`docs/reference/configuration.md`):
  expanded to document all 11 `[defaults]` keys (`mode`, `persist`, `store`,
  `timeout`, `trust_scan`, `max_size`, `max_age`, `adapters`, `log_level`,
  `log_file`, `version`), the `[executables]` section, the `version` key
  semantics, the full precedence order, default config-file and store
  locations per OS, and the `config validate` / `config show` commands.

### Changed

- **CLI and daemon READMEs** (docs): removed all cross-package references.
  `packages/cli/README.md` no longer installs or links to the daemon package.
  `packages/daemon/README.md` no longer documents `gmlcache` CLI commands —
  direct launch via `python -m generic_ml_cache_daemon` is the only
  documented start method.

## [0.25.0] - 2026-06-28

### Added

- **Extended `gmlcache doctor`** (cli): text and `--json` output now include Python
  version, OS, config file path, store path, store permissions (exists / readable /
  writable), and daemon reachability (HTTP `/health` probe). `--json` carries all new
  fields alongside the existing `clients`, `schema`, and `adapter_extensions` keys.
- **`gmlcache doctor --bundle`** (cli): writes the full diagnostic payload to a
  timestamped `gmlcache-bundle-<ts>.json` file in the current directory; no credentials
  are included in the payload. `--bundle` and `--json` are mutually exclusive.
- **`--host` / `--port` on `doctor`** (cli): controls where the daemon reachability
  probe connects; defaults match `daemon start` (`127.0.0.1:8765`).
- **PII scrubbing structlog processor** (common): a `_scrub_processor` runs in the
  structlog chain after exception tracebacks are rendered. Redacts e-mail addresses
  (`[email]`), bearer/API token header values (`[token]`), long opaque strings that
  look like API keys or encryption tokens (`[secret]`), and values stored under
  sensitive key names (`token`, `password`, `api_key`, etc.) (`[redacted]`). Pure
  lowercase-hex strings (SHA-256 content-addressed keys) are intentionally preserved.

### Fixed

- **Daemon encryption token wiring** (daemon): `create_app()` now reads `GMLCACHE_TOKEN`
  from the daemon's own environment and passes it to `build_use_cases()`. Previously the
  token was ignored, making gateway mode and store encryption mutually exclusive.
  The token is never included in the gateway URL — it stays in the daemon's process
  environment and is never visible to the proxied client.

### Changed

- **`docs/compatibility.md`** (docs): clarified the `--json` row in the stability table
  — lists the 15 reporting commands that support it and explicitly calls out that
  write-and-action commands (`run`, `encrypt`, `daemon start`, etc.) do not.

## [0.24.0] - 2026-06-28

### Added

- **Compatibility policy** (`docs/compatibility.md`): written policy covering what is
  stable at 1.0.0 (CLI surface, public Python API, adapter contract, execution-record
  schema, configuration keys), the Python version support range and drop cadence
  (CPython 3.9–3.13, dropped no sooner than EOL), the 1.x schema promise (additive-only
  within 1.x, automatic migration on startup), the adapter contract promise
  (`adapter_contract_version = "1"` stable across all 1.x releases), and the migration
  path from any 0.17.0+ store to 1.0.0 (one binary run, no manual SQL).

## [0.23.0] - 2026-06-28

### Added

- **Public API boundary** (core): `generic_ml_cache_core.__init__` now declares an
  explicit `__all__`. The stable public surface is: `build_use_cases`, `WiredUseCases`,
  `RunMlExecutionCommand`, `ClientAdapter`, `MlRunnerPort`, `register`, `get_adapter`,
  the full `CacheError` hierarchy (`CacheMiss`, `UnknownClient`, `ConfigError`,
  `ClientNotFound`, `CommandLineTooLong`, `InputFileError`, `ArtifactBlobMissing`,
  `WrongEncryptionToken`, `EncryptionTokenRequired`, `EncryptionStateError`,
  `StoreLocked`, `RunInterrupted`), and the checksum utilities (`checksum_input_data`,
  `text_checksum`, `file_content_fingerprint`). Everything else (`adapter/`,
  `application/`, `common/`, `migrations/`) is internal and may change between minor
  versions.
- **DB-agnostic SQL layer** (core): `DbConnection` / `DbCursor` Protocols (PEP 249)
  replace all `sqlite3.Connection` imports in core. SQLite-specific constructs
  removed: `INSERT OR IGNORE` → `WHERE NOT EXISTS`, `ON CONFLICT DO UPDATE` →
  UPDATE + rowcount check, `PRAGMA user_version` → `schema_version` table,
  `BEGIN EXCLUSIVE` file lock → `fcntl`/`msvcrt` OS-level lock. A new import-linter
  contract (Rule 5) permanently enforces that `sqlite3` may not be imported anywhere
  inside `generic_ml_cache_core`.

## [0.22.0] - 2026-06-28

### Added

- **Machine-readable error codes** (core): each `CacheError` subclass now carries a
  stable `code: ClassVar[str]` attribute — e.g. `"cache.miss"`, `"store.locked"`,
  `"crypto.wrong_token"`. The code is accessible on both the class and any raised
  instance. `RunInterrupted` (not a fault) has no code.
- **Daemon unified error handler** (daemon): a single `@exception_handler(CacheError)`
  registered in `create_app()` maps every error code to its HTTP status and returns a
  consistent JSON body `{"code": "…", "detail": "…"}`. Per-controller ad-hoc
  `HTTPException` wrapping is gone.
- **README badge redesign**: replaced the combined CLI/API adapter badges and the
  pyright/import-linter badges with six individual per-adapter badges — each badge links
  directly to the adapter's source file in the repository.

### Error code → HTTP status table

| Code | Status | Meaning |
|---|---|---|
| `cache.miss` | 404 | Offline mode: no stored execution matches |
| `adapter.unknown` | 400 | No adapter registered for the requested client name |
| `adapter.not_found` | 400 | Client executable not on PATH |
| `adapter.command_too_long` | 400 | Assembled argv exceeds OS limit |
| `config.invalid` | 422 | Config file or env var value is invalid |
| `input.file_error` | 422 | Declared input file unreadable |
| `store.blob_missing` | 404 | Artifact record exists but bytes are gone |
| `crypto.wrong_token` | 401 | Token cannot decrypt the store's wrapped data key |
| `crypto.token_required` | 401 | Encrypted store but no token supplied |
| `crypto.state_error` | 409 | Encryption operation conflicts with store state |
| `store.locked` | 409 | Another process holds the exclusive store lock |

## [0.21.0] - 2026-06-28

### Added

- **`gmlcache.adapters` entry point group** (core): third-party adapter packages
  declare an entry point in this group and their adapter is discovered at runtime
  without any change to core — the Python `ServiceLoader` equivalent of the existing
  `@adapter` built-in scanner. Install the package, and the adapter is available.
- **Adapter contract version** (core): `ADAPTER_CONTRACT_VERSION = "1"` constant
  introduced. Third-party adapters may declare `adapter_contract_version = "1"` as a
  class attribute to assert compatibility; a mismatch emits a `warnings.warn` and the
  adapter is skipped. Absence of the attribute is treated as compatible.
- **`adapter_sources(whitelist)`** (core): new registry function returning
  `{name: "package version"}` for installed entry-point adapters only. Built-in
  adapters and programmatically registered adapters are omitted.
- **`gmlcache doctor` — adapter extensions section** (cli): the doctor command now
  shows an "installed adapter extensions" section listing each entry-point adapter and
  the package that contributed it. The `--json` path gains an `"adapter_extensions"`
  key. Both are empty/absent when no third-party adapters are installed (no change to
  existing output).

## [0.20.0] - 2026-06-28

### Added

- **McCabe C901 complexity gate** (cli, daemon): `ruff` lint rule `C901` enabled with
  `max-complexity = 10`; functions exceeding the ceiling fail the pre-commit hook and
  CI. Existing violations resolved as part of the decomposition.

### Changed

- **Hexagonal decomposition of `cli.py`** (cli): the 2720-line God Module split into
  `controllers/` (eight command-group modules), `presenters/` (shared rendering and
  session report), `infrastructure/` (argument parser and entry point), and
  `composition.py` (dependency-wiring helpers). `cli.py` is retained as a
  backward-compatible re-export shim.
- **Daemon layer rename** (daemon): `routes/` → `controllers/`, `models/` →
  `presenters/`, `middleware/` → `infrastructure/` — both packages now share the same
  hexagonal vocabulary.
- **Status-line formatter** (tools): `tools/claude-code/format-status-line.py`
  redesigned with per-field width budgets and smart clipping, multi-line cache output
  (session and per-model token detail on separate lines below git/cwd/quota), normalized
  model names (`claude-sonnet-4-6-20250919` → `sonnet`), and readable text prefixes
  (`quota`, `PR`, `cache`) replacing icon glyphs.

## [0.19.0] - 2026-06-28

### Added

- **`DiagnosticsPort`** (core): new hexagonal outbound port
  (`application/port/out/diagnostics_port.py`) with `debug`, `info`, `warn`, and
  `error` severity levels plus structured `**context` kwargs. Core never imports a
  logging library directly; it emits through this port.
- **`NullDiagnosticsAdapter`** (core): silent no-op default
  (`application/port/out/null_diagnostics_adapter.py`). Wiring this adapter
  guarantees diagnostics can never reach the replay channel by construction.
- **`StructlogDiagnosticsAdapter`** (common): `structlog`-backed implementation in
  `packages/common`; supports logback-style text output (default) and JSON output
  (`--log-format json`). Rotates daily with 7-day retention; never raises (R5
  contract).
- **Trace-style entry/exit logging** (core): every meaningful operation in
  `CachedMlExecutionService`, `PurgeService`, `RunMlGatewayService`,
  `RunMlExecutionService`, `AccessRegistry`, `migration`, and `discover` now logs
  ENTER, EXIT with `duration_ms`, and FAILED on unexpected exceptions.
- **`--log-file` / `--log-format` / `--log-level` flags** (cli): all `gmlcache`
  subcommands accept these flags to enable and configure the diagnostics log.
  `doctor` and `models` pass the live adapter to `schema_version` and `probe_all` /
  `list_models_all`.
- **Daemon diagnostics wiring** (daemon): `app.py` reads `LOG_FILE`, `LOG_FORMAT`,
  and `LOG_LEVEL` environment variables and wires the `StructlogDiagnosticsAdapter`
  at startup.
- **`structlog>=21` dependency** (cli, daemon): added to both packages for
  Python 3.9+ compatibility.

## [0.18.0] - 2026-06-27

### Added

- **Unified SQLite database** (core, cli, daemon): `executions.sqlite3` and
  `registry.sqlite3` are merged into one file. All tables — `call_identities`,
  `executions`, `artifacts`, `token_usage`, `execution_tags`, `access_events`,
  `session_tags`, `session_specs` — live in a single database owned by the CLI or
  daemon caller.
- **Schema migration runner** (core): `adapter/inbound/migration.py` provides
  `run_migrations(conn_factory)` and `schema_version(conn_factory)`. Migrations are
  pure SQL files in `core/migrations/`, tracked with SQLite's built-in
  `PRAGMA user_version` (no external dependency). Each migration is applied
  atomically inside a single `BEGIN EXCLUSIVE / COMMIT` block.
- **`packages/common`** (internal): shared `datasource.py` with a
  `sqlite_connection_factory(path)` helper used by both CLI and daemon to build the
  injected `conn_factory`.
- **`FilesystemStoreLock`** (core): replaces `SqliteStoreLock`. Renamed to reflect
  that SQLite is the locking mechanism (OS-level file lock via `BEGIN EXCLUSIVE`),
  not the subject of the lock. Behaviour is unchanged.
- **`gmlcache doctor` shows schema version** (cli): the `doctor` command now prints
  how many migrations are applied and the latest migration ID; `--json` includes a
  `"schema"` key.
- **`tools/gateway-probe/probe.py`**: standalone HTTP probe server for manual
  gateway integration testing.
- **`tools/claude-code/settings.json`**: committed Claude Code settings template
  (status-bar wiring); the `format-status-line.py` script moved from `scripts/` to
  `tools/claude-code/`.

### Changed

- **`build_use_cases` signature** (core, cli, daemon): first parameter is now
  `conn_factory: Callable[[], Connection]` instead of `store_root: Path`. Core no
  longer calls `sqlite3.connect()` internally — connection ownership belongs to the
  caller.
- **`SqliteExecutionRepository`** (core): accepts `conn_factory` instead of a file
  path; removed the self-contained `_ensure_schema()` setup call.
- **`AccessRegistry`** (core): accepts `conn_factory` instead of `root: Path`;
  removed `_ensure_*` guards (schema is guaranteed by `run_migrations`).

### Removed

- **`yoyo-migrations` dependency** (core): replaced by the built-in
  `PRAGMA user_version` migration tracker. Eliminates a runtime dependency that
  called `socket.getfqdn()` on every first migration run — a 30+ second hang on
  macOS-15/26 GitHub Actions runners (upstream: actions/setup-python#1223).
- **`sqlite_store_lock.py`** (core): renamed to `filesystem_store_lock.py`.

## [0.17.0] - 2026-06-27

### Added

- **`py.typed` markers** (core, cli): both packages now ship `py.typed`; consumers
  get IDE type inference and type-safe imports without extra stubs.
- **`import-linter` hexagonal contracts** (quality): four contracts enforced in CI —
  application-ring isolation (core may not import from `adapter`), driver-package
  isolation (cli/daemon may not import `adapter.out` directly), domain purity, and
  adapter isolation. Zero violations at release.
- **`pyright` type-checking gate** (quality): all 51 pre-existing type errors resolved;
  pyright now runs clean as a hard CI gate.
- **Pre-commit hooks** (quality): `pre-commit` config adds `ruff`, `lint-imports`, and
  `pyright` hooks; `AGENTS.md` documents the green definition.
- **Claude Code status-bar script** (`tools/claude-code/format-status-line.py`):
  two-line status bar with git branch, CI/PR state, store quota, and auto-refresh;
  hyperlinked PR numbers via OSC 8 terminal escape.
- **README quality badges and adapter matrix** (docs): CI, PyPI, and licence badges;
  table of supported adapters and storage backends.

## [0.16.0] - 2026-06-27

### Added

- **Unified adapter registry** (core): `adapter/registry.py` replaces the split
  `client/registry.py` and `api/api_registry.py`. A single registry keyed on
  `MlRunnerPort.name` now covers both local-managed and API adapters.
  `load_adapters(whitelist)` drives all resolution; `registered_names()` returns all
  adapters; `registered_local_names()` returns `LOCAL_MANAGED` adapters only.
- **`@adapter` class decorator** (core): marks a built-in adapter class for automatic
  discovery by the built-in scanner (`pkgutil.iter_modules`). Replaces explicit
  `register()` calls in each built-in module.
- **Adapter whitelist** (cli, daemon): a `FrozenSet[str]` whitelist that threads
  through the entire stack — `build_use_cases`, `probe_all`, `list_models`,
  `list_api_models`, and every registry lookup. Configure in the config file with
  `adapters = *` (all active), `adapters = claude, cursor` (named filter), or omit
  (same as `*`). Referencing an adapter outside the whitelist fails immediately with
  a clear `UnknownClient` error.
- **`GMLCACHE_ADAPTERS` env var** (daemon): `*` or a comma-separated name list;
  parsed on startup and passed to `create_app` as the daemon whitelist.
- **`gmlcache status` shows active adapter filter** (cli): text mode reports
  `* (all active)` or `<name>, <name>  (from config)`; `--json` includes an
  `"adapters"` field (`null` for all-active, sorted list when filtered).
- **`gmlcache daemon start` threads whitelist from config** (cli): passes
  `file_cfg.adapters` to `create_app`, so the daemon inherits the config-file filter.
- **`GET /info` reports filtered adapter list** (daemon): the `adapters` field in the
  info response reflects the active whitelist rather than the full installed set.
- **`UnknownClient` caught in run/alias error path** (cli): a whitelisted-out adapter
  now returns exit 4 with a clear message in both `gmlcache run` and `gmlcache alias`,
  rather than an unhandled exception.

### Removed

- `adapter/out/client/registry.py` (core): replaced by the unified registry.
- `adapter/out/api/api_registry.py` (core): replaced by the unified registry.

## [0.15.0] - 2026-06-27

### Added

- **`max_age` config setting** (cli): new `max_age` key in `[defaults]` (e.g. `max_age = 30d`)
  and matching `GMLCACHE_MAX_AGE` environment variable. Accepted suffixes: `s`, `m`, `h`, `d`,
  `w`. Parsed with the same unit-aware parser as `max_size`. Shown in `gmlcache status`.
- **`PurgeService.evict_stale(max_age_seconds)`** (core): soft-purges current executions whose
  last access (from the access journal) is older than the configured cutoff. Entries that have
  never been accessed fall back to their `created_at` timestamp. Zero or negative values are a
  no-op.
- **`EvictionScheduler`** (daemon): asyncio background task that runs `evict_to_quota` and/or
  `evict_stale` on a configurable interval (default 1 hour). Wired into the FastAPI lifespan;
  starts only when at least one limit (`max_size` or `max_age`) is configured.
- **Eviction stats in `GET /info`** (daemon): response now includes an `eviction` object with
  `max_size`, `max_age`, `interval`, `last_run_at`, `last_executions_removed`, and
  `last_bytes_freed` — the result of the most recent sweep.
- **`gmlcache daemon start` threads eviction config** (cli): reads `max_size` and `max_age`
  from the resolved config and passes them to `create_app`, so the daemon respects eviction
  settings when started via the CLI.
- **`GMLCACHE_EVICTION_INTERVAL`** (daemon): environment variable to override the default
  1-hour sweep interval (in seconds). Useful for testing and automated environments.
- **Eviction demo tapes** (docs): `docs/tapes/evict-lru.tape` and `docs/tapes/evict-stale.tape`
  demonstrate LRU quota enforcement and scheduled stale eviction with the enriched fake client.
  All tapes moved from `docs/` to `docs/tapes/`.
- **Enriched fake client** (docs): `render-tape.py` fake client now reads the prompt from stdin
  and echoes it back (`Cached: <prompt>`), making `list` output meaningful in eviction demos.
- **Retention docs updated** (docs): `docs/concepts/retention.md` gains a "Scheduled stale
  eviction" section covering `max_age`, `GMLCACHE_EVICTION_INTERVAL`, and the `/info` eviction
  field; `docs/reference/cli.md` gains an "Automatic eviction" subsection with GIF anchors.

## [0.14.0] - 2026-06-26

### Added

- **`gmlcache status-line`** (cli): new top-level subcommand that fetches live session
  stats from the daemon (`GET /sessions/{id}/stats`) and prints the raw JSON to stdout.
  Reads the session from `GMLCACHE_SESSION` or `--session`; reads the daemon address from
  `--host` / `--port` (defaults `127.0.0.1:8765`). Exits 0 silently when no session is
  set or the daemon is not running — safe for repeated polling from a status bar.
- **`scripts/format-status-line.py`** (scripts): cross-platform Python formatter that
  assembles a single Claude Code status-bar line from four independent sections — git
  context (repo, branch, HEAD hash, dirty-file count), abbreviated current working
  directory, gmlcache session stats (calls, hits, hit rate, per-model token breakdown with
  cache-read / cache-write / reasoning token counts), and a Claude Max quota widget
  (`3% : 3h58m  ·  66% 1d3h`) read from the OAuth token Claude Code stores in
  `~/.claude/.credentials.json`. Each section is silently skipped if its source is
  unavailable. Results are cached for 60 s to avoid excessive API calls.
- **`docs/shell-integration.md`** (docs): documented shell integration examples for
  Linux/macOS (bash/zsh function) and Windows (PowerShell function) showing how to create
  a gmlcache session, start the daemon, and launch Claude Code through the gateway in one
  command. Framed as copy-and-adapt snippets, not maintained scripts.
- **`.claude/settings.json`** (project): project-level Claude Code configuration wiring
  `scripts/format-status-line.py` as the `statusLine` command.
- **Extended token fields in session stats** (core + daemon): `ModelUsage` (core) and
  `ModelUsageBody` / `SessionStatsResponse` (daemon) now include `cache_read_tokens`,
  `cache_write_tokens`, and `reasoning_tokens`. `GET /sessions/{id}/stats` returns these
  fields per model alongside the existing `spent_input` / `spent_output` / `saved_tokens`.
- **Gateway session routing** (core + daemon): session ID now travels in the URL path
  (`/gateway/claude/{session_id}/v1/messages`) so the daemon is fully stateless and
  multiple sessions can share one daemon simultaneously. Full request and response bodies
  are stored on every forwarded call; forwarded calls emit `RECORD` (not `MISS`) so token
  counts appear correctly in session reports.

### Removed

- **`scripts/launch-claude.sh`** and **`scripts/launch-claude.ps1`**: shell scripts
  removed; replaced by the documented examples in `docs/shell-integration.md`.

## [0.13.0] - 2026-06-25

### Added

- **Daemon transport** (daemon): `generic-ml-cache-daemon` — a new, independently
  versioned package that wraps the core execution engine in a local FastAPI + Uvicorn HTTP
  server. REST endpoints cover cache runs (sync and SSE streaming), detached jobs, session
  CRUD, session stats, and a Claude pass-through gateway at
  `/gateway/claude/v1/messages`. Auto-generated OpenAPI/Swagger UI at `/docs`.
  `gmlcache daemon start | status | stop` drives the lifecycle from the CLI.
- **Session execution spec** (core + cli + daemon): `session start` accepts
  `--client / --model / --effort` to attach a complete execution spec to a session.
  Runs within that session inherit the spec; partial specs are rejected at creation time.
  `session update` replaces the spec atomically; `session clear-spec` removes it.
  The spec is validated at runtime against the active adapter whitelist.
- **Session tag removal** (cli): `session tag <id> --remove <tag>` — complement to
  `--add` from 0.12.0.
- **Session stats endpoint** (daemon): `GET /sessions/{id}/stats` returns call count,
  hit count, hit rate, and per-model token sums (input, output, saved) for a session.
- **Gateway routing** (daemon): the daemon uses the session spec as its routing
  directive; calls arriving for one adapter can be transparently redirected to the adapter
  configured in the session.

## [0.12.0] - 2026-06-25

### Added

- **Session tags** (core + cli): sessions carry tags — the same concept as execution
  tags, applied one level up. `session start --tag <tag>` attaches tags at creation;
  `session tag <id> --add <tag>` adds tags after the fact. `session report --tag <tag>`
  aggregates all sessions sharing that tag. `list --session-tag` supports cross-level
  queries combining execution tags and session tags.

## [0.11.0] - 2026-06-25

### Added

- **Retention and invalidation** (core + cli): size-based cache quotas and explicit
  invalidation commands. `gmlcache purge --max-size` enforces a store-size ceiling;
  `gmlcache invalidate` removes specific entries by key or tag. Metadata-driven cleanup
  operates on the existing SQLite store with no schema changes.

## [0.10.0] - 2026-06-25

### Added

- **API adapters** (core + cli): three direct REST adapters — `--client anthropic`,
  `--client openai`, `--client gemini` — call provider APIs without a local binary.
  All use stdlib `urllib`; no new runtime dependencies. Each adapter maps the
  provider's token fields into the common usage envelope:
  - **Anthropic**: Messages API; maps all four token fields including
    `cache_write_tokens` (the only provider that reports it).
  - **OpenAI**: Responses API; maps `cache_read_tokens` (automatic, read-only cache)
    and `reasoning_tokens`.
  - **Gemini**: generateContent REST API; maps `reasoning_tokens` from
    `thoughtsTokenCount`. Extended thinking is supported via the `thinking` config.
  - `cost_usd` is always `None` — none of the three providers return a dollar figure
    per call; tokens are the unit, no pricing table is bundled.
  - `gmlcache models <client>` queries the provider's live model list for all three.
  - Auth via environment variable: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
    `GEMINI_API_KEY`.

### Changed

- **Unified runner port** (core): the three separate execution paths (managed local,
  passthrough local, API) are collapsed into a single `MlRunnerPort` / `MlRequest`
  model. All six adapters (three CLI, three API) implement the same port; the
  composition root selects the adapter by `--client` name. `ModelListingPort` is a
  separate, optional interface — an adapter that supports model listing implements it;
  discovery uses `isinstance`, no separate registry.

## [0.9.0] - 2026-06-24

### Added

- **Alias mode** (cli): `gmlcache alias <client> -- <native args...>` — a thin native-client
  wrapper. Everything after the client is an opaque tail, forwarded to the client verbatim and
  keyed (by fingerprint) as the cache identity; gmlcache models or auto-completes nothing. Its
  own options (`--mode` / `--offline` / `--force`, `--persist`, `--record-on-error`,
  `--executable`, `--token`, `--session`, `--timeout`) come **before** the client; an optional
  `--` separator keeps a dash-leading tail from fighting the parser. A replay reproduces the
  native call's stdout, stderr and exit code — but, unlike a managed `run`, alias mode does no
  isolation and no file capture, so generated files are written by the live call only and a
  recorded failure is never served as a hit. Reuses core's existing passthrough engine; for
  input fingerprinting, generated-file replay, grants, or detached execution, use `run`.

## [0.8.0] - 2026-06-24

### Added

- **Asynchronous executions** (cli): `gmlcache run --detach` submits a managed run as a detached
  background job and prints an execution id immediately; the work continues in a separate,
  OS-detached worker process and is recorded into the normal cache. Manage it with `gmlcache
  execution status | result | watch | materialize | list <id>`. Job state lives under
  `<store>/jobs/`; a per-job liveness lock (SQLite `BEGIN EXCLUSIVE`, released by the OS when the
  worker dies) lets a reader tell a live worker from one that vanished mid-run — reported as
  **interrupted**, never a hang. `watch` replays the durable, ordered event log from the start
  (a late watcher still sees every event) and follows it live. A detached run never writes
  generated files to the caller's cwd (the launch has returned) — `execution materialize <id>
  --output-dir <path>` writes them on demand. Detach is managed-only; on an **encrypted** store
  pass `--token` / `GMLCACHE_TOKEN` — it is handed to the worker through its environment (never
  written to disk), and `result` / `materialize` take `--token` to decrypt.
- **Live progress streaming** (core + cli): `run --stream [PATH]` writes a live NDJSON event
  stream as a call runs — `run.start`, the client's own `start` / `thinking` / `tool` / `result`
  events (claude, codex, and cursor are all normalized), and `run.end` — that a human or a
  parent process can `tail -f`. Display-only: it never changes what is recorded or the cache
  key (give a path, or `--stream` alone writes `./gmlc-stream.jsonl`). The same sink backs
  detached jobs, so `execution watch` now shows the client's real live progress interleaved with
  the job lifecycle, not just state transitions.

## [0.7.0] - 2026-06-24

### Added

- **Session reporting** (core + cli): `gmlcache session report <id>` now aggregates token usage
  and activity for a session. Tokens are grouped **by provider/model** — spent (input/output)
  and **saved** by cache hits — never summed across models; activity is broken down **by day**
  (a session can span days) with a small bar; the header shows the day span. `--json` emits the
  structured report. There are **no dollar figures** (a cost estimate is a client-specific
  advisory number), and executions that reported no usage are counted as *unknown*, never folded
  in as zero. The aggregation is a pure, unit-tested function over the journal events joined to
  each execution's usage.

## [0.6.0] - 2026-06-23

### Added

- **Sessions** (core + cli): group one workflow's runs under a session id so they can be
  reported together. `gmlcache session start` generates an id (scriptable);
  `gmlcache run --session <id>` / `GMLCACHE_SESSION` attaches a run to it; `gmlcache session
  report <id>` rolls up the session — invocations (every call), executions (the calls that
  ran), hits (served from cache), and the per-event breakdown (`--json` too). Built on the
  existing invocation journal: a session is that journal filtered to a session id, with an
  additive, self-migrating `session_id` column. The id is journal metadata only — never part
  of the cache key (the same input under different sessions is one entry), and sessions span
  every run kind (managed, passthrough, API). Reporting is metadata-only, so it works on an
  encrypted store without the token. Per-session token usage and cost is a later, richer report.

### Changed

- The CLI banner now renders the gmlcache mark, and its tagline reflects the shipped features
  (`record · replay · check · sessions · encryption`).

## [0.5.0] - 2026-06-23

### Added

- **At-rest encryption** (core + cli): optional, token-keyed encryption of the stored content.
  `gmlcache encrypt` enables it — gmlcache generates a high-entropy token (no outside
  passwords), encrypts the store, and prints the token once; `decrypt` (with the token) returns
  it to plaintext, `rotate` swaps the token (re-wrapping the data key — content is never
  re-encrypted), and `invalidate --yes` crypto-shreds the store (the escape when the token is
  lost). Content commands (`run`, `export`) take `--token` / `GMLCACHE_TOKEN`; metadata-only
  commands need no token, and `status` shows the state.
  Envelope encryption (AES-256-GCM + HKDF-SHA256): content is encrypted under a random data key
  that is itself wrapped under the token; only non-secret material is stored — never the token
  or the key. Encryption is **store-wide and all-or-nothing**, and transparent to the cache key
  (the token is never part of identity). The enable/disable migration is crash-safe (stage →
  atomic commit marker → per-file swap; an interrupted migration self-heals on the next open).
  Ships behind an optional, permissively-licensed, pip-only `[encryption]` extra; the base
  install is unaffected. Covers the content blobs (prompts/outputs/inputs); execution metadata
  (fingerprints, model names, tags) stays plaintext — see the data-handling note.

## [0.4.0] - 2026-06-23

### Added

- **Persistence depth** (core + cli): a single ordered `--persist` choice over what each
  call keeps on disk — `meter` (usage/metadata only, never replays), `cache` (+ output, the
  default — today's replay behaviour), or `dataset` (+ input). Each level is a superset of the
  last, so the degenerate "input stored without output" state is unrepresentable. Set it per
  call (`gmlcache run --persist <depth>`) or as a default via the `persist` config key or
  `GMLCACHE_PERSIST` (precedence: flag > env > config > built-in `cache`); `gmlcache status`
  shows the resolved value. Replaces the former internal `persist_output` boolean. `meter`
  **never replays** — it always runs and stores nothing, but journals whether the call *would*
  have hit a stored entry (`would_hit` / `would_miss`, visible in `gmlcache stats`), so you can
  measure "you'd have saved N runs" without a cache.
- **Dataset corpus and export** (core + cli): at `dataset` depth a call's input is kept beside
  the output as content-addressed `INPUT_*` artifacts, forming a labelled `(input, output)`
  corpus; persistence depth behaves the same for every execution kind — managed-local stores
  context/prompt/system, the API kind stores its message list, and passthrough its native-arg
  vector. `gmlcache inspect` shows whether an entry's input was stored. `gmlcache export` emits
  the corpus as JSONL (to stdout or `--output FILE`). Export yields a **raw** corpus — entries
  stored below `dataset` depth carry no input and are skipped and reported, never silently
  dropped. Input **accumulates on a hit**, like tags: re-running an already-cached call at
  `dataset` depth back-fills the input onto the existing entry (no re-run needed), so you can
  upgrade a plain cache entry into a dataset entry by changing your mind.
- **Tag discovery and exclusion** (cli): `gmlcache tags` lists the distinct tags in use across
  current executions, with counts; `gmlcache list --exclude-tag` and `gmlcache export
  --tag`/`--exclude-tag` filter by tag (match-any include and exclude, with exclude winning).
  This is how a dataset is curated — the cache never judges output quality; there is
  deliberately no built-in quality flag (quality is just a user-chosen tag).

## [0.3.0] - 2026-06-22

### Added

- **Tags** (core + cli): label executions with user-supplied tags for grouping and
  later queries. `gmlcache run … --tag <name>` (repeatable) tags an execution, and
  relabeling an already-cached input **accumulates** tags onto the entry;
  `gmlcache list --tag <name>` filters by tag (match-any) and every listed entry shows
  its tags. Tags are a **separate annotation** — metadata only, never part of the cache
  key, and adding one never rewrites an execution.

## [0.2.0] - 2026-06-22

### Changed

- **Restructured into a monorepo of two packages** (core, cli): the library
  `generic-ml-cache-core` (the engine — domain, use cases, ports, and the default
  adapters; stateless and dependency-free) and the client `generic-ml-cache-cli` (the
  `gmlcache` terminal UI). The engine is now embeddable in any application by injecting
  a data source; the CLI is one inbound driver over it. The two packages are versioned
  in lockstep.
- **Rebuilt on a hexagonal (ports-and-adapters) architecture** (core): the engine
  depends only inward; concrete adapters (client runner, SQLite execution repository,
  filesystem blob store, metrics, clock, fingerprint) implement ports owned by the
  core and are wired by a `build_use_cases` composition factory.

### Removed

- **Retired the on-disk "cassette" record format** (core): executions are now stored
  as structured records in a SQLite repository plus a content-addressed blob store for
  output bytes. As before, only fingerprints are persisted — never raw prompts or
  context.

## [0.1.0] - 2026-06-20

**Documentation and specification reset** (ROADMAP 0.1.0): the docs now describe
the system as it actually behaves.

### Changed

- **Documentation restructured into a layered set** — `architecture/`,
  `concepts/`, `reference/`, `future/`, and `use-cases/` trees plus a docs index
  and a new root README, replacing the flat `docs/*.md`. The conceptual model is
  defined end to end (execution request, cassette, adapters, access registry,
  usage envelope), with storage, eviction, grants, and generated-file replay
  documented. Community and legal files unchanged.

### Added

- **Reference aligned with the code** — complete `run`/`check` options; the real
  configuration keys with their `GMLCACHE_*` environment overrides, precedence,
  and file/store locations; the cassette per-file entry (`path`/`content`/
  `encoding`); and how a grant is opened (the uniform per-client config-file
  mechanism). Not-yet-built capabilities (async, scopes/sessions, alias) are
  clearly marked future.

## [0.0.16] - 2026-06-20

### Added

- **`run --json`.** `run` now accepts `--json`, emitting a machine-readable envelope
  -- status, exit, files, the answer, and the **normalized usage** dict (the same
  shape `check --json` exposes: input/output/cache-read/cache-write/reasoning tokens
  and the advisory cost) -- instead of the raw answer. This lets a parent process
  (the workflow engine reading per-call usage for its cost view) get the result and
  the usage in one parse after a real execution; files are still written to the cwd.

### Changed

- **Grants are now opened by a config file, not a flag — one uniform mechanism for
  all three clients.** The cache writes each client's own configuration into a
  redirected config home (`CLAUDE_CONFIG_DIR` → `settings.json`, `CODEX_HOME` →
  `config.toml`, `CURSOR_CONFIG_DIR` → `cli-config.json`), seeding credentials, and
  runs the client with that home. This replaces the 0.0.15 per-client net doors
  (Claude inline `--settings`, Codex `-c network_access`, Cursor `--force`-only).
  The home is separate from the run folder, so the settings file and seeded
  credentials never enter a cassette.

### Added

- **Grants now cover five capabilities** — `net`, `read`, `write`, `shell`,
  `web-search` — on `run` and `check`, each keyed into the call (its own cassette)
  and cacheable. Run-folder write stays on by default; the named grants open
  capability beyond it. Enablement only: Codex has no file-level deny for read/shell
  and Cursor none for read (documented limits, not doors the cache closes); Cursor's
  external network egress keeps `--force` as a forced transport flag. `--grant` on
  the CLI now lists all five values in `--help`. Validated 2026-06-18 against the
  live CLIs; see [`docs/reference/grants.md`](docs/reference/grants.md).

## [0.0.15] - 2026-06-18

### Added

- **Grants (`run --grant net`).** Open a capability for the launched client; the
  first is `net` (web / network access). It extends the write/trust door from
  "write inside the run folder" to "reach the network when a step needs a live
  source." A granted call is keyed (a net call gets its own, inspectable cassette)
  and cached like any other call -- `--force` re-fetches live. Enablement only: the
  cache opens doors, never closes them, and is not a security boundary (see
  [`docs/reference/grants.md`](docs/reference/grants.md)). Available on `run` and `check`. All three net
  doors are verified against the live CLIs: Codex via its `workspace-write` sandbox
  network toggle, Claude via a web-tool allow-list in a settings file (the narrow
  `--allowedTools` flag proved flaky), and Cursor via `--force`
  (its `--trust` write door alone does not open Cursor's sandboxed network).
- **`inspect` accepts a short key**, not only a file path: paste the key shown by
  `list` and it's resolved against the store. A path still works; an unknown key
  fails cleanly, and an ambiguous prefix lists the candidates.

## [0.0.14] - 2026-06-18

### Added

- **Shell completion** for commands and flags via `argcomplete` (Apache-2.0 — now
  the one runtime dependency). Activate with `eval "$(register-python-argcomplete gmlcache)"`.
- **`list`** — a read-only listing of stored cassettes grouped by client/model,
  each row showing effort, short key, size, cache-hit count, and the file path
  (paste into `inspect`). `--client`/`--model` narrow it; `--json` for programmatic use.
- **A banner in the help.** A bare `gmlcache` now prints the banner followed by the
  help and exits `0`, instead of an argparse error; the banner also fronts `-h`.
  Colour is dropped when output is not a terminal (piped, redirected, or `NO_COLOR`).

### Fixed

- **`inspect` fails legibly** on a missing, unreadable, or malformed cassette — a
  clean `gmlc:` message and exit `4`, instead of a Python traceback.

## [0.0.13] - 2026-06-18

### Added

- **Passthrough client arguments (`--client-arg`).** An escape hatch for client
  features the cache does not model: extra arguments appended verbatim to the
  client launch, available on both `run` and `check`. They are **part of the
  key** — the same modeled inputs with different passthrough args are a different
  call and get their own cassette — but only their **fingerprint** is stored, so
  raw args (which may carry secrets) never land in a cassette. Each client places
  them as late as its CLI still reads them as flags (before the prompt, where the
  prompt is a trailing positional). Repeatable and order-significant; pass a
  dash-leading value with the =form (`--client-arg=--flag`).

## [0.0.12] - 2026-06-17

### Added

- **`check` — a read-only cache probe.** Given the same inputs as `run`, it
  answers whether the call is already cached — **hit / miss / non-cacheable** —
  and on a hit reports the cassette's file count and its recorded usage/cost. It
  launches no client and writes nothing: a forecast, not a replay, so a caller
  (the workflow engine) can tell which calls would hit before committing to a run.
  Human output by default, `--json` for programmatic use. The exit code is `0` for
  every verdict — cached-or-not is the result, carried in the output, not the exit
  code; only real errors (bad client/config) are non-zero. `run` and `check` share
  their key derivation, so a probe can never disagree with a run.

## [0.0.11] - 2026-06-17

### Added

- **Usage and cost are now captured on every call.** Each cassette records a
  usage block: a **normalized** envelope common to all clients — input, output and
  cache-read tokens, plus an optional ring (cache-write, separated reasoning,
  dollar cost) — alongside the **client's raw usage block kept verbatim**, so a
  field we did not normalize is still reachable. Tokens are the spine; a dollar
  figure is recorded only when the client reports one (today, only Claude) and is
  flagged as the client's own estimate, not authoritative billing. A count the
  client does not report stays **unknown** (never silently `0`) — so a reported
  zero and an absent field stay distinct.
- **`inspect` shows the usage envelope**, with `--raw` to print the client's
  verbatim block.
- **`stats` reports tokens saved** across replays: every cache hit avoided a real
  call, so its recorded usage is usage not spent; the readout sums input, output
  and cache-read tokens (and an estimated dollar saving when client costs are
  known), noting any replays whose cassette carried no usage so the figure is not
  understated.

### Changed

- **Clients are now invoked in their structured (JSON) output mode** so the call
  also returns its usage. Each adapter lifts the clean answer text back out of the
  structured output, so the caller still receives plain text on stdout exactly as
  before — the cache, not the caller, parses the client's output. Claude:
  `--output-format json`; Codex: `exec --json` (a JSON-lines event stream); Cursor:
  `--print --output-format json`.
- **Cassette schema is now version 2** (adds the optional `usage` field). Older
  (version 1) cassettes still load unchanged — their usage is simply *unknown*.

## [0.0.10] - 2026-06-17

### Added

- **Legible failure when a prompt is too large to launch.** Before starting a
  client, the cache measures the assembled command line against the operating
  system's argument-size limit (~32 KB on Windows, 128 KiB per argument on Linux,
  `ARG_MAX` on macOS) and, if it would be exceeded, fails with a clear message —
  the size, the limit, and the remedy (declare input files, or use a stdin-based
  tier) — instead of an opaque "argument list too long" error or a silent Windows
  failure. In practice this only affects cursor, whose prompt rides in argv;
  claude and codex deliver the prompt on stdin and never hit it.

### Changed

- **Claude and Codex prompts are delivered on stdin, not as a command-line
  argument.** Both adapters now feed the prompt and context through the client's
  stdin — the launcher already pipes stdin cross-platform via Python
  (`communicate`), with no shell — so an arbitrarily large prompt can no longer hit
  the OS single-argument size limit (128 KiB per argument on Linux, the ~32 KB
  whole-command-line cap on Windows, `ARG_MAX` on macOS); this was a real failure
  once an uncompressed prompt crossed ~131 KB. It is delivery-only: the cassette
  key is unchanged. Closing stdin on EOF also avoids the `codex exec` hang in a
  non-TTY child. Claude reads stdin with `-p` and no prompt argument; Codex via the
  `codex exec -` placeholder.

  **Cursor is the exception:** `cursor-agent` takes the prompt only as a positional
  argument (its CLI has no stdin/file path — verified against `cursor-agent
  --help`), and feeding it on stdin makes it hang. So the cursor adapter keeps the
  prompt in argv, which means a **cursor prompt is bounded by the OS argument-size
  limit** — a cursor CLI constraint the cache cannot work around, not a regression.

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

[Unreleased]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.16.0...HEAD
[0.16.0]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.14.0...v0.15.0
[0.1.0]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.16...v0.1.0
[0.0.16]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.15...v0.0.16
[0.0.15]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.14...v0.0.15
[0.0.14]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.13...v0.0.14
[0.0.13]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.12...v0.0.13
[0.0.12]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.11...v0.0.12
[0.0.11]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.10...v0.0.11
[0.0.10]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.9...v0.0.10
[0.0.9]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/danielslobozian/generic-ml-cache/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/danielslobozian/generic-ml-cache/releases/tag/v0.0.1
