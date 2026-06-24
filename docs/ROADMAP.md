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
  feature has landed (gateway, daemon, and SDK adapters included), the **alpha tag is
  removed**, and the CLI surface, execution-record schema, and adapter contract are locked
  under a compatibility policy.

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

### 0.10.0 — API adapters

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

### 0.11.0 — Retention and invalidation

- Size quotas.
- Explicit invalidation commands.
- Metadata-driven cleanup. Single-user; no per-scope policy.
- Time-based cleanup is deferred to the daemon milestone (requires a resident process).

### 0.12.0 — Session tags

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

### 0.13.0 — Daemon transport

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
- Transport-level live status and events.
- Ships as a **dedicated, independently-versioned package** (`generic-ml-cache-daemon`),
  versioned against a `generic-ml-cache-core>=X` range.
- Strictly local and single-user — see [Positioning](design/positioning.md).

### 0.14.0 — Scheduled eviction

Time-based cache maintenance, enabled by the resident daemon from 0.13.0.

- TTL-based and stale-entry cleanup configured in the store settings.
- Complements the size-based eviction introduced in 0.11.0.
- Eviction events surfaced through the daemon's live status reporting.

### 0.15.0 — SDK adapters and dynamic adapter loading

Replace the stdlib `urllib`-based API adapters and CLI subprocess wrappers with official
provider SDKs; split adapters out of `core` into dedicated optional packages. Use Python
entry points for automatic discovery.

- **SDK adapters** (3 CLI agent SDKs + 3 provider API SDKs) become the canonical
  implementations. `core` ships no concrete adapters — only the ports and the entry-point
  discovery loop.
- **Adapter packages** (`generic-ml-cache-adapters-cli`,
  `generic-ml-cache-adapters-anthropic`, etc.) declare `gmlcache.adapters` entry points.
  Installing a package makes its adapter available; not installing it leaves 0 adapters for
  that provider.
- **Unified registry**: the current `client/registry` and `api/api_registry` are merged
  into a single registry keyed on `MlRunnerPort.name`, populated at startup by scanning
  entry points.
- `ModelListingPort` stays as an opt-in interface (`isinstance` check); no separate
  registry needed.

### 1.0.0 — Stable, feature-rich cache

- Everything above shipped and productionised.
- Alpha tag removed.
- Stable CLI surface under a compatibility policy.
- Stable execution-record schema and compatibility policy.
- Stable adapter contract — including verifying the per-client read-permission mechanism
  currently confirmed only for Claude.
- Public documentation aligned with actual behavior.

## After 1.0.0

The dedicated adapter packages (`generic-ml-cache-adapters-*`) and the daemon package
(`generic-ml-cache-daemon`) will version independently against a
`generic-ml-cache-core>=X` compatibility range once 1.0.0 has locked the core contract.
Core and cli remain lockstep; the surrounding ecosystem can evolve at its own cadence.

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
