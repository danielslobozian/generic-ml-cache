<div align="center">

# Roadmap

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

## At a glance

- [Current alpha capability](#current-alpha-capability)
- [Road to 1.0.0: a stable, feature-complete cache](#road-to-100-a-stable-feature-complete-cache)
- [After 1.0.0](#after-100)
- [Out of scope unless explicitly revisited](#out-of-scope-unless-explicitly-revisited)

---

This roadmap describes intended direction. It is not a promise of dates.

The current ruling for versioning is:

- `0.x.y` remains **alpha**: the execution-record schema, CLI surface, and adapter
  contract may still change while the feature set is being built.
- The `0.x` line builds toward a **stable, feature-complete `1.0.0`** — not a thin
  "current capability" release. Each `0.x` minor lands a feature milestone; `y` covers
  fixes and small corrections.
- `1.0.0` is the **stable, feature-rich** release — the point at which every planned
  feature has landed (gateway, daemon, dynamic adapter loading, and developer tooling
  included), the **alpha tag is removed**, and the CLI surface, execution-record schema,
  and adapter contract are locked under a compatibility policy.

Schema-shaping features (persistence, sessions) deliberately land **before** `1.0.0`,
while `0.x` still permits the record schema to change — so `1.0.0` can lock a schema that
is already session-aware rather than promise stability it would soon have to break.

The data-handling features (tagging, persistence, encryption) are **orthogonal, composable
toggles**, not one feature; their model and the cryptographic cautions are recorded in the
[data-handling design note](design/data-handling.md).

## Current alpha capability

The current implementation already provides:

- exact content-addressed recording and replay,
- detached CLI adapters for supported clients,
- isolated execution folders,
- generated-file capture,
- declared input file checksums,
- allow-path and scan-trust behavior,
- grants where supported by adapters,
- usage capture where clients expose structured output,
- `check`, `list`, `inspect`, `stats`, `doctor`, `models`, and `status`,
- an access registry for non-load-bearing observability.

Size-based eviction is **configured but not yet enforced** (`max_size` is reserved);
it is part of the retention milestone below.

## Road to 1.0.0: a stable, feature-complete cache

### 0.1.0 — Documentation and specification reset *(released 2026-06-20)*

- Replace historical docs with current conceptual documentation.
- Define execution request, execution record, adapter, registry, and usage envelope.
- Document storage, eviction, grants, and generated-file replay clearly.
- Keep community/legal files unchanged.

### 0.2.0 — Restructure, quality gates, and release automation *(released 2026-06-22)*

Delivered the planned code-structure work **plus** the quality-gate and packaging
milestones originally scoped as 0.3.0 and 0.4.0 — they were ready, so they shipped here.

- Split into a monorepo of two lockstep packages: the `generic-ml-cache-core` library
  (domain, use cases, ports, and the default adapters; stateless) and
  the `generic-ml-cache-cli` client (`gmlcache`).
- Rebuilt on a hexagonal (ports-and-adapters) architecture; retired the on-disk
  "cassette" record format for a SQLite execution repository + content-addressed blobs.
- Quality gates: SonarQube Cloud with coverage, ruff lint/format, a cross-platform
  OS/Python test matrix, and branch protection requiring green checks.
- Release automation: GitHub Actions CI and PyPI **Trusted Publishing** via OIDC
  (no stored tokens); documented install and release.

### 0.3.0 — Tags

Free-form labels for grouping and querying executions. No prerequisites — pure metadata.

- A call may carry 0, 1, or many user-supplied tags.
- Tags are **metadata only**: they never enter execution identity (the fingerprint), so
  the same input under different tags remains one cache entry.
- Executions become queryable by tag (`list` / report filters).
- Tags are stored verbatim and never interpreted.

### 0.4.0 — Persistence depth (meter / cache / dataset)

A single ordered choice over what each execution keeps on disk — each level a superset of
the last, so the degenerate "input without output" state cannot be expressed. See the
[data-handling design note](design/data-handling.md).

- **meter**: metadata/usage only — every call runs, no replay; pairs with tags for
  cost/usage analytics and can report *would-be* hit/miss without storing anything.
- **cache** *(default)*: + output — replay on hit (today's behavior).
- **dataset**: + input — replay **and** a queryable, labeled `(input, output)` corpus,
  exportable as JSONL for distillation/evaluation. Export yields a **raw** corpus; curation
  stays the user's, via tags (`export --tag` / `--exclude-tag`) — the cache never judges
  output quality, so there is no built-in quality flag.

### 0.5.0 — Encryption at rest

Optional, token-keyed encryption of persisted data — the privacy boundary, and the only
thing the old "scope token" idea survives as: a single, optional **cryptography token** (no
scope identity, no namespaces). See the [data-handling design note](design/data-handling.md)
for the cryptographic cautions.

- All-or-nothing: when on, persisted input **and** output are encrypted under a key derived
  from the user's encryption secret.
- The token is supplied at runtime (`GMLCACHE_TOKEN` or `--token`) and **never stored**;
  gmlcache keeps only non-secret derivation material. Lost token = unrecoverable, which is also
  the erasure property (invalidate = crypto-shred).
- Protects data at rest (disk theft, backups); does not protect a compromised running process.
- Ships behind an optional extra (the encryption library is the dependency), so the base
  install is unaffected.

### 0.6.0 — Sessions

Sessions group the executions of one workflow — single-user, no namespace above them.

- Session IDs are generated by gmlcache (`session start`); a session needs only an id (no
  token, no account). Attach a run with `run --session <id>` or `GMLCACHE_SESSION`.
- A session is the append-only invocation journal filtered to a session id. `session report`
  rolls up invocations / executions / hits; per-session token usage and cost is 0.7.0.
- Sessions do not participate in execution identity.

### 0.7.0 — Session reporting

- Aggregate a session's usage **by provider/model** (a token means nothing without them) and
  its activity **by day** (sessions can cross days).
- Report invocations / executions / hits, and tokens **spent** vs **saved** by cache hits.
- Tokens are the unit; **no dollar figures** (a cost estimate is client-specific and advisory).
  Usage a call did not report is **unknown**, never zero.
- Observational only.

### 0.8.0 — Asynchronous executions

- `run --detach` submits a managed run as a detached worker process and returns an execution id.
- `execution status` / `list` query state; a per-job liveness lock distinguishes a live worker
  from one that vanished mid-run (**interrupted**).
- `execution watch` replays and follows the durable event log.
- `execution result` fetches the final output; `execution materialize` writes generated files
  explicitly — a detached run never writes them into the caller's folder (the launch has exited).
- Managed-only. On an encrypted store the token is handed to the worker through its
  environment (never written to disk), so detached runs encrypt their results too.

### 0.9.0 — Alias mode *(released 2026-06-24)*

Alias mode is a thin native-client wrapper mode.

- Everything after the selected adapter is treated as native adapter arguments.
- The raw argument tail is part of cache identity.
- No attempt is made to auto-complete or model every native client option.
- Alias mode is for users who want native client behavior plus basic caching.

### 0.10.0 — API adapters *(released 2026-06-25)*

Direct REST adapters for provider APIs — peers to the existing CLI adapters, using the
same execution request model, caching engine, and persistence layer.

- **Anthropic** (`--client anthropic`): Messages API via stdlib urllib; maps all four
  token fields including `cache_write_tokens` (the only provider that reports it).
- **Google Gemini** (`--client gemini`): generateContent REST API via stdlib urllib;
  maps `reasoning_tokens` from `thoughtsTokenCount`.
- **OpenAI** (`--client openai`): Responses API via stdlib urllib; maps
  `cache_read_tokens` (automatic, read-only cache) and `reasoning_tokens`.
- `cost_usd` is always `None` for API adapters — none of the three providers return a
  dollar figure per call. Tokens are the unit; no pricing table is bundled.
- Cursor has **no inference API** and stays as a CLI adapter only.
- Provider names are resolved automatically from the `--client` value: no separate
  `--provider` flag is needed.
- No new runtime dependencies — all three adapters use stdlib `urllib`.

### 0.11.0 — Retention and invalidation *(released 2026-06-25)*

- Size quotas.
- Explicit invalidation commands.
- Metadata-driven cleanup. Single-user; no per-scope policy.
- Time-based cleanup is deferred to the daemon milestone (requires a resident process).

### 0.12.0 — Session tags *(released 2026-06-25)*

Sessions carry tags — the same concept as execution tags, applied one level up. A session
may have zero, one, or many tags; none are required.

- `session start --tag <tag>` attaches tags at creation (repeatable).
- `session tag <id> --add <tag>` adds tags to an existing session after the fact.
- `session report --tag <tag>` aggregates all sessions sharing that tag.
- `list` gains `--session-tag` for cross-level queries: combine `--tag` (execution tag)
  and `--session-tag` (session tag) to express queries like "executions tagged
  `code-analysis` within sessions tagged `feature`."
- Session tags are **metadata only**: a session without tags behaves exactly as today and
  session tags never enter execution identity.

### 0.13.0 — Daemon transport *(released 2026-06-25)*

A resident local process that exposes the same execution engine through a local HTTP
interface — another *interface* over the same engine, never another engine and never a
multi-user service. See the [daemon transport design note](future/daemon-transport.md).

- **Local pass-through proxy**: point your own ML client at the daemon by setting
  `ANTHROPIC_BASE_URL=http://localhost:<port>` (or the equivalent for other providers).
  Every underlying API call the client makes is intercepted, cached, and traced — whether
  you drive the cache explicitly via `gmlcache run` or let the client call the API
  naturally, all calls land in the same store.
- **Session binding**: start the daemon with a session id
  (`gmlcache daemon start --session <id>`) and every intercepted call records under that
  session. Composing with session tags enables a clean shell alias — create the session,
  start the daemon bound to it, set the base URL, then launch the client; all in one
  command.
- **Session execution spec**: at `session start`, optionally attach a complete execution
  spec — adapter, model, and effort. All three move together; partial specs are rejected.
  Effort may be empty for adapters that bake it into the model name (Cursor). Runs within
  that session inherit the spec without the caller repeating it. The spec is always
  validated at runtime against the active adapter whitelist — if the adapter has been
  removed from the whitelist since the session was created, the call fails immediately
  with a clear error.
- **Session spec mutation**: `session update --client <a> --model <m> [--effort <e>]`
  replaces the spec atomically, forward-only — past runs are unaffected.
  `session clear-spec <id>` removes the spec entirely without requiring empty fields.
- **Session tag removal**: `session tag <id> --remove <tag>` (complement to `--add`
  from 0.12.0).
- **Gateway routing**: the daemon uses the session spec as its routing directive — a call
  arriving from one adapter can be transparently redirected to the adapter configured in
  the session, enabling subscription-aware routing without any change to the calling
  client.
- **HTTP API**: FastAPI (MIT) + Uvicorn (MIT) expose every cache operation as a REST
  endpoint with auto-generated OpenAPI/Swagger UI at `/docs`. Synchronous and
  SSE-streaming runs share the same `POST /run` endpoint via content negotiation
  (`Accept: text/event-stream`). Detached jobs use a two-step model: `POST /jobs`
  returns a `job_id`; `GET /jobs/{id}/stream` is the SSE event tail.
- **Gateway endpoints**: `POST /gateway/claude/v1/messages` speaks the Anthropic
  Messages API protocol. Each adapter that supports gateway mode gets its own mount
  point (`/gateway/<client>/...`) so the client's existing base-URL setting points
  straight at it. Starting with Claude only; further adapters added as the ecosystem
  warrants.
- **Session stats** (`GET /sessions/{id}/stats`): call count, hit count, hit rate,
  per-client breakdown, and token sums (`input_tokens`, `output_tokens`,
  `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`) — each summed over
  non-null reported values for the session. This is the endpoint the 0.14.0 status
  bar polls.
- **Observability**: `GET /health` (liveness), `GET /ready` (readiness),
  `GET /info` (version, store path, active adapters), `GET /metrics`
  (Prometheus, `prometheus-client` Apache 2.0, off by default).
- **Testing**: `starlette.testclient.TestClient` (MIT) drives every endpoint in
  unit tests without starting a server — the FastAPI community standard, analogous
  to Spring MockMvc. Core use cases are injected as mocks; a small number of
  integration tests run against a real in-memory store.
- Ships as a **dedicated, independently-versioned package** (`generic-ml-cache-daemon`),
  versioned against a `generic-ml-cache-core>=X` range.
- Strictly local and single-user — see [Positioning](design/positioning.md).

### 0.14.0 — Developer status bar and shell integration examples *(released 2026-06-25)*

A Claude Code status bar and documented shell integration patterns for live session
visibility. Depends on the daemon HTTP API from 0.13.0.

- **Shell integration examples** (`docs/shell-integration.md`): documented patterns
  (bash/zsh function for Linux and macOS, PowerShell equivalent for Windows) showing
  how to create a session, start the daemon, and launch Claude Code with the gateway
  configured in one command. These are copy-and-adapt examples, not maintained scripts
  that ship as a product.
- **Status bar** (`scripts/format-status-line.py`): a Python script wired into Claude
  Code's `statusLine` setting that polls the daemon's session endpoint and displays
  live stats — call count, cache hit count, and per-model token usage — updating as
  the session progresses. Platform-neutral; works on Linux, macOS, and Windows via
  the same file.
- **Claude quota display**: the status bar also shows Claude Max usage for the current
  5-hour block and 7-day window (`3% : 3h58m  ·  66% 1d3h`), read from the OAuth
  token Claude Code stores locally. Cached for 60 s; silently omitted when unavailable.
- The status bar makes the cache's behaviour visible without leaving the editor: call
  counts accumulate in real time, hit/miss ratio builds, and the active adapter is always
  visible — even when the underlying client has made many more calls than the user
  explicitly triggered.

### 0.15.0 — Scheduled eviction *(released 2026-06-27)*

Time-based cache maintenance, enabled by the resident daemon from 0.13.0.

- **`max_age` config setting** (`max_age = 30d` / `GMLCACHE_MAX_AGE`): configures the maximum
  time since last access before an entry is considered stale. Accepted suffixes: s/m/h/d/w.
- **`PurgeService.evict_stale()`** (core): soft-purges entries older than the cutoff; falls back
  to `created_at` for entries that have never been accessed.
- **`EvictionScheduler`** (daemon): asyncio background task running both `evict_to_quota` and
  `evict_stale` on a configurable interval (default 1 h, overridable via
  `GMLCACHE_EVICTION_INTERVAL`). Started only when at least one limit is configured.
- **Eviction stats in `GET /info`**: `last_run_at`, `last_executions_removed`, `last_bytes_freed`,
  `max_size`, `max_age`, and `interval` surfaced in the daemon's info endpoint.
- **`gmlcache daemon start`** now threads `max_size` and `max_age` from the resolved config into
  the daemon, so both LRU and stale eviction are active when started via the CLI.
- **Demo tapes** (`docs/tapes/evict-lru.tape`, `docs/tapes/evict-stale.tape`): VHS cassettes
  demonstrating both eviction modes; all tapes moved to `docs/tapes/`.

### 0.16.0 — Dynamic adapter loading and adapter whitelist *(released 2026-06-27)*

Replace the split static registries with a unified registry; add a config-driven
whitelist to control which adapters are active at runtime. Third-party entry-point
discovery is 0.20.0; SDK adapters are post-1.0.0.

- **`@adapter` decorator**: marks a class for automatic discovery by the built-in
  scanner (`pkgutil.iter_modules`); replaces explicit `register()` calls in the
  built-in adapter modules.
- **Unified registry** (`adapter/registry.py`): the split `client/registry` and
  `api/api_registry` are merged into a single registry keyed on `MlRunnerPort.name`.
  `load_adapters()` drives all resolution; `registered_names()` returns all adapters,
  `registered_local_names()` returns `LOCAL_MANAGED` adapters only.
- **Adapter whitelist**: configure in the config file with `adapters = *` (all
  active), `adapters = claude, cursor` (named filter), or omit (same as `*`).
  Threads through `build_use_cases`, `probe_all`, `list_models`, and
  `list_api_models`; also accepted by the daemon via `GMLCACHE_ADAPTERS`.
  Removing an adapter from the whitelist causes any call referencing it to fail
  immediately with a clear error.
- `ModelListingPort` stays as an opt-in interface (`isinstance` check); no separate
  registry needed.
- `gmlcache status` reports the active adapter filter; `gmlcache daemon start`
  threads the whitelist from config into the daemon.

### 0.17.0 — Type checking gate, hexagonal boundary enforcement, and `py.typed` markers *(released 2026-06-27)*

Two new quality gates (import-linter and pyright) mechanically enforce the hexagonal
architecture boundaries that were previously only documented as rules. All violations
those gates expose are fixed before the gates go green.

- **`py.typed` markers** added to all three packages; consumers get IDE type inference
  and type-safe imports without installing stubs.
- **`import-linter`** added to CI as a hard gate; a single `.importlinter` at the repo
  root declares four hexagonal contracts across all three packages:
  - *Application ring isolation*: `generic_ml_cache_core.application` may not import
    from `generic_ml_cache_core.adapter` — the hexagonal invariant; dependencies point
    inward, never outward.
  - *Driver packages*: `generic_ml_cache_cli` and `generic_ml_cache_daemon` may not
    import from `generic_ml_cache_core.adapter.out` — drivers work through ports and
    the composition root, never past it into driven-adapter implementations.
  - *Domain purity*: `generic_ml_cache_core.application.domain` may not import from
    `generic_ml_cache_core.application.usecase` — domain objects model the world,
    not workflows.
  - *Adapter isolation*: driven adapter sub-packages must not import each other —
    cross-adapter wiring belongs exclusively in the composition root.
- **`pyright`** (basic mode) added to CI as a hard gate; failures block merge. A
  root-level `pyrightconfig.json` covers all three packages.
- **Violations fixed** (all violations exposed by the new gates resolved before the
  gate goes green):
  - `WiredUseCases` fields re-typed as port interfaces (`ExecutionRepositoryPort`,
    `MetricsPort`) instead of concrete adapter classes — the composition root must
    not leak adapter types into the application ring.
  - `current_execution_summaries()` and `find_current_by_key_prefix()` promoted from
    the SQLite adapter to `ExecutionRepositoryPort`, removing the only remaining
    non-port CLI-to-adapter calls.
  - `ExecutionSummary` dataclass moved from the adapter file to the domain/port layer
    where it belongs.
  - CLI's direct `adapter.out` imports (crypto, lock, discover modules) encapsulated
    behind port or composition-root calls.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): both `lint-imports` and `pyright`
  run as a local commit-time gate backed by the project's own `.venv` — violations
  are caught before `git commit` writes, so malformed code never reaches history.
- **AGENTS.md** gains gates 6 (`lint-imports`) and 7 (`pyright`) — no interpretive
  rules, just "run these tools."
- **README badges**: `pyright` (passing) and `import-linter` (4 contracts) badge row
  added; client adapter compatibility matrix and storage backend table added.
- **Status bar enhancements** (`scripts/format-status-line.py`):
  - PR/CI section added (⤴ `#<number>` with coloured ✓/✗/⋯ check counts and 💬
    comment count); auto-detects `gh` (GitHub) or `glab` (GitLab); OSC 8 hyperlink
    on the PR number for Ctrl/Cmd-click.
  - Two-line layout: git · cache · cwd · quota on line 1; PR/CI directly below the
    branch name on line 2.
  - `refreshInterval: 30` in `.claude/settings.json` — re-runs the script every 30 s
    so CI counts update without requiring user interaction.
  - Reads Claude Code's stdin JSON for `cwd` and rate-limit quota — eliminates the
    Anthropic API call for subscribers; falls back to the API when `rate_limits` is
    absent.

### 0.18.0 — DB architecture redesign and SQLite schema migrations *(released 2026-06-27)*

Core has accumulated schema changes across `0.x` releases with no formal migration
story, and the current `build_use_cases(store_root)` pattern violates the
ports-and-adapters contract by having core spawn SQLite files internally. This
milestone fixes the architecture and introduces a proper migration layer.

**Architecture change (non-negotiable):**
Core is a pure library and may not spawn databases. The new contract is:
- **Core owns** the schema SQL and the migration runner (pure DBAPI2-agnostic SQL).
- **The caller** (CLI or daemon) owns the datasource (the connection).
- `build_use_cases` is refactored to accept a pre-built PEP 249 `Connection` instead
  of a `store_root: Path`. Core never calls `sqlite3.connect()` directly.
- `packages/common/` (a plain folder, no separate PyPI package) provides shared schema
  SQL and the migration runner, referenced via hatchling `packages` config in both CLI
  and daemon `pyproject.toml`.

**Single unified DB:** the two SQLite files (`executions.sqlite3` and
`registry.sqlite3`) are merged into one. The `session_specs` table is load-bearing
(gateway routing), which invalidates any "non-load-bearing" justification for a
separate file.

**Migration layer:**
- **`schema_version` table**: recorded on first startup; tracks the applied migration
  sequence so each migration is idempotent and the current version is always known.
- **Migration runner**: executes ordered migration scripts at startup; no manual
  intervention required for in-place upgrades from any prior `0.x` release.
- Pure SQL — no ORM, no SQLAlchemy. DBAPI2-agnostic: the same runner works with
  `sqlite3`, `psycopg2`, or any PEP 249 compliant driver.
- **`gmlcache doctor`** reports the current schema version alongside existing diagnostics.
- **1.0.0 compatibility promise**: any store created by a `0.x` release can be upgraded
  to the 1.0.0 schema by a single run of the new binary.
- No automatic backup — the store is local and single-user; docs recommend a manual
  copy before upgrading from `0.x`.

### 0.19.0 — Technical diagnostics logging *(released 2026-06-28)*

A second, distinct observability subsystem — technical diagnostics — added as a pure
hexagonal outbound port. The journal (product observability) is untouched and
unchanged; the two subsystems serve different readers and must never be merged.

**What each subsystem answers:**

| | Journal *(exists)* | Diagnostics *(this milestone)* |
|---|---|---|
| Question | *What happened to the cache?* | *Why did the code do that?* |
| Vocabulary | Closed — a fixed set of named events | Open — severity levels |
| Shape | Named events | DEBUG / INFO / WARN / ERROR |

**Decided (durable):**

- **R1 — Hexagonal port**: core emits through a `DiagnosticsPort`; it never imports a
  logging library directly. Core holds the equivalent of `Logger`; the edge holds the
  equivalent of `logback.xml`.
- **R2 — Severity-leveled**: the port speaks DEBUG / INFO / WARN / ERROR. No named-event
  vocabulary; that model belongs to the journal. A diagnostic event name lives inside the
  line as plain, greppable text — never as a pre-declared enum.
- **R3 — Edges configure**: the CLI and daemon each supply the concrete adapter — level
  threshold, format, destination. None of those decisions exist in core.
- **R4 — Fidelity safe by construction**: because core can only emit through the port
  and the edge owns the destination, the CLI adapter is built so diagnostics can never
  reach the replay channel. Quiet mode emits zero diagnostics. The byte-exact replay
  contract is protected structurally — not by convention.
- **R5 — Never-raise**: a diagnostics failure must never break or alter an execution —
  the same contract the metrics port already holds.
- **R6 — One context source**: structured context (execution key, session id, client,
  model, effort) is derived from the same envelope that already feeds the journal; no
  parallel context variables.
- **R7 — Quality floor on first write**: diagnostic event tokens and field names reveal
  content; logs are greppable and meaningful from the name alone. The quality floor is
  cleared on first write, not deferred.

**Highest-value instrumentation points** (to guide the build, not its contract):

1. The currently-silent swallow points on the metrics/observability path — the single
   biggest usability win, as failures there are invisible today.
2. The cache-resolution decision branch (which branch and why) at DEBUG.
3. The client / gateway invocation boundary.

**Open questions (reserved for the implementation session):**

- Concrete port method shape and signatures.
- CLI flags and their names/defaults (level, format, file); whether the logger plumbs
  into the existing `-v/--verbose gmlc:` channel or sits beside it.
- Text vs JSON defaults per surface; the daemon's default format.
- Destinations (stderr vs file vs both) per surface.
- Build order — CLI-first vs daemon-first.

Ships under the two-commit release rule.

### 0.20.0 — CLI decomposition and complexity gate

`cli.py` has grown to 2,600+ lines and 79 functions — a God Module. This milestone
decomposes it into a `commands/` package and enforces a complexity ceiling in CI.

- **`commands/` package**: each command group (`run`, `alias`, `session`, `daemon`,
  `execution`, `list`, `inspect`, `doctor`, `models`, `config`, `encrypt`) becomes
  its own module; shared helpers (`output`, `errors`) extracted where they serve more
  than one command.
- **McCabe complexity gate** (C901): added to the ruff lint config with a threshold
  of 10; CI fails on any function exceeding it. Current violations (`_cmd_purge` at 12,
  `_communicate_streaming` at 17, and three others) resolved as part of the
  decomposition.
- **Test infrastructure**: `fake_client.py` currently duplicated verbatim in both
  `packages/core/tests/` and `packages/cli/tests/`; the duplicate removed, canonical
  location retained.

### 0.21.0 — Third-party adapter entry points

0.16.0 shipped the `@adapter` decorator and built-in scanner for adapters within
`generic_ml_cache_core`. Third-party adapters — packages such as
`generic-ml-cache-adapter-ollama` — require a proper Python entry-point mechanism.

- **`gmlcache.adapters` entry point group**: adapter packages declare an entry point
  in this group; installing the package makes its adapter available without any change
  to core.
- **Discovery priority**: entry-point adapters are loaded alongside built-ins; the
  whitelist applies uniformly to both.
- **Adapter contract version**: declared so third-party adapters can assert
  compatibility with the core version they target.
- **`gmlcache doctor`** reports entry-point adapters alongside built-ins, with their
  source package noted.

### 0.22.0 — Error taxonomy: machine-readable codes

The exception hierarchy in `common/errors.py` is well-structured. This milestone adds
machine-readable `code` attributes to enable programmatic handling by library consumers
and consistent HTTP responses from the daemon.

- Each `CacheError` subclass gains a stable `code: str` class attribute
  (e.g. `"cache.miss"`, `"adapter.unavailable"`, `"store.locked"`).
- The daemon maps each code to its HTTP status; error responses carry the code in
  the JSON body.
- The CLI renders each error class consistently; no behavioral change for existing users.
- The code namespace is documented as part of the stable public API (see 0.23.0).

### 0.23.0 — Public API boundary

`generic-ml-cache-core` is a library. Without a declared public surface, consumers can
import any internal path and receive a silent breakage on upgrade.

- Explicit `__all__` on `generic_ml_cache_core.__init__`; anything not listed is
  internal and may change between minor versions.
- The public surface is: `build_use_cases`, `WiredUseCases`, `RunMlExecutionCommand`,
  `ClientAdapter`, `MlRunnerPort`, `register`, `get_adapter`, all error types from
  `common/errors.py`, and the checksum utilities.
- `generic-ml-cache-cli`'s re-export surface aligned and documented.
- Internal module paths (`adapter/out/…`, `adapter/inbound/…`, persistence internals)
  documented as internal in the architecture docs.

### 0.24.0 — Compatibility policy

A written compatibility policy is required for 1.0.0 to be a promise rather than a label.

Documents:

- What is stable at 1.0.0: CLI surface, execution-record schema, adapter contract,
  public API (`__all__` from 0.23.0).
- What can change between `0.x` minor versions (alpha; no stability guarantee).
- The supported Python version range and its update cadence.
- The execution-record schema compatibility promise: what a 1.x binary guarantees
  about stores created by earlier 1.x releases.
- The adapter contract compatibility promise: what a third-party adapter written
  against 1.0.0 can rely on across 1.x releases.
- The migration promise: what a user must do to move from any `0.x` store to 1.0.0
  (one run of the new binary; see 0.17.0).

### 0.25.0 — Doctor diagnostic bundle

Strengthen `gmlcache doctor` from a client-availability check into a full operational
diagnostic surface.

- **`gmlcache doctor --json`**: machine-readable output of every diagnostic field;
  the existing text output is unchanged.
- **Extended fields**: Python version, OS, config path, store path, current schema
  version (from 0.17.0), store permissions, and daemon reachability.
- **`gmlcache doctor --bundle`**: writes the full diagnostic to a timestamped file
  for support purposes; any sensitive value (token, API keys) is redacted before
  writing.

### 0.26.0 — Configuration schema versioning and validation

- **`gmlcache config validate`**: parses and validates the config file without
  executing anything; reports all errors and warnings and exits non-zero on any
  error. Distinct from a run — purely a diagnostic.
- **`gmlcache config show --resolved`**: displays the fully resolved configuration
  across all sources (default → file → env → flag) as structured output. Distinct
  from `gmlcache status`, which shows runtime and store state; this shows only
  configuration resolution.
- **`version` key**: config file gains an optional `version` key; future config
  schema changes check it to detect stale files and emit a clear migration message.
- Documentation covers the config schema exhaustively: every key, accepted values,
  default, and resolution order.

### 1.0.0 — Stable, feature-rich cache

- Everything above shipped and productionised.
- Alpha tag removed.
- Stable CLI surface under a compatibility policy.
- Stable execution-record schema and compatibility policy.
- Stable adapter contract — including verifying the per-client read-permission mechanism
  currently confirmed only for Claude.
- Public documentation aligned with actual behaviour.

## After 1.0.0

The dedicated adapter packages (`generic-ml-cache-adapters-*`) and the daemon package
(`generic-ml-cache-daemon`) will version independently against a
`generic-ml-cache-core>=X` compatibility range once 1.0.0 has locked the core contract.
Core and cli remain lockstep; the surrounding ecosystem can evolve at its own cadence.

**SDK adapters** (replacing the stdlib `urllib` API adapters and CLI subprocess wrappers
with official provider SDKs) are a post-1.0.0 nice-to-have. The entry-point mechanism
from 0.20.0 means SDK adapters can be introduced as new adapter packages without any
change to the core.

## Out of scope unless explicitly revisited

- Semantic caching.
- Interpreting model output to infer dependencies.
- Interactive session capture.
- Hosted multi-tenant authentication.
- Security sandboxing claims.
- Provider billing authority.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
