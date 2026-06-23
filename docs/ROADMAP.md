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
- [After 1.0.0: dedicated releases](#after-100-dedicated-releases)
- [Out of scope unless explicitly revisited](#out-of-scope-unless-explicitly-revisited)

---

This roadmap describes intended direction. It is not a promise of dates.

The current ruling for versioning is:

- `0.x.y` remains **alpha**: the execution-record schema, CLI surface, and adapter
  contract may still change while the feature set is being built.
- The `0.x` line builds toward a **stable, feature-complete `1.0.0`** — not a thin
  "current capability" release. Each `0.x` minor lands a feature milestone; `y` covers
  fixes and small corrections.
- `1.0.0` is the **stable, feature-rich** release: tagging, persistence depth, at-rest
  encryption, sessions, reporting, asynchronous executions, alias mode, API adapters, and
  retention have all landed, and the CLI surface, execution-record schema, and adapter
  contract are locked under a compatibility policy.
- After `1.0.0`, the **daemon transport ships as a dedicated, independently-versioned
  package**: core and cli stay lockstep, but the daemon versions on its own cadence
  against a `generic-ml-cache-core>=X` compatibility range, so a daemon-only change
  never bumps core or cli.

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
- Managed-only; encryption + detach is a later step (the token must not land on disk).

### 0.9.0 — Alias mode

Alias mode is a thin native-client wrapper mode.

- Everything after the selected adapter is treated as native adapter arguments.
- The raw argument tail is part of cache identity.
- No attempt is made to auto-complete or model every native client option.
- Alias mode is for users who want native client behavior plus basic caching.

### 0.10.0 — API adapters

- Add provider API adapters as peers to CLI adapters.
- Preserve the execution request model.
- Capture usage and cost metadata when providers expose it.
- Keep provider-specific behavior inside adapters.

### 0.11.0 — Retention and invalidation

- Size quotas.
- Explicit invalidation commands.
- Time-based stale-entry cleanup (with the daemon).
- Metadata-driven cleanup. Single-user; no per-scope policy.

### 1.0.0 — Stable, feature-rich cache

- Everything above, productionized.
- Stable CLI surface under a compatibility policy.
- Stable execution-record schema (tag- and session-aware) and compatibility policy.
- Stable adapter contract for the CLI and API adapters — including verifying the
  per-client read-permission mechanism currently confirmed only for Claude.
- Public documentation aligned with actual behavior.

## After 1.0.0: dedicated releases

These land after the stable release. The daemon is a separate, independently-versioned
package; scheduled eviction depends on it.

### Daemon transport — *dedicated package*

- Expose the same execution engine through a resident local service.
- Provide transport-level live status/events.
- Keep daemon mode as another interface, not another engine.
- Ships as its own package (`generic-ml-cache-daemon`), versioned independently against a
  `generic-ml-cache-core` compatibility range rather than in lockstep with core and cli.

### Scheduled stale-entry eviction

- Time-based eviction for entries stale beyond a configured age.
- Requires a resident process or explicit maintenance command (pairs with the daemon).
- Complements, but does not replace, the size-based eviction introduced with retention.

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
