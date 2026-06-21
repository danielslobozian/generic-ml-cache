# Domain Model & Target Design

> **Status: BUILD.** All names and structural decisions in this document are
> settled. The model is being implemented slice by slice on the
> `hexa-refactoring` branch. Items still open for future work are marked
> **OPEN**; those are decisions deferred deliberately, not forgotten.
>
> Companion to `AGENTS.md`. AGENTS.md is the **how** (the enforceable coding
> standard); this is the **what** (the specific objects, names, and homes). They
> cross-reference and stay separate.

---

## 1. The core reframe

The project began as a **cache**: store a *cassette* (inputs, key, outputs), and on
a matching input, replay it. As it grew — direct client calls, streaming,
events, token/session statistics, execution types that deliberately do not store
output — the cassette stopped being the thing the system is *about*.

The tell: a `LOCAL_PASSTHROUGH` execution (one that runs but stores no output)
has no cassette, yet is unmistakably a real thing — it has inputs, it ran, it
produced output, it cost tokens. If the cassette were the aggregate, that call
would be nothing. It is obviously *something*.

**Decision: the aggregate is `MlExecution`.** The cassette concept is fully
retired (see §4).

---

## 2. The aggregate — `MlExecution`

An `MlExecution` is a demand to run an ML client and what came back. It is the
aggregate root.

```
MlExecution
  call_identity    : CallIdentity      -- the value object that determines the key
  execution_state  : ExecutionState    -- IN_PROGRESS | SUCCESS | FAILED
  execution_kind   : ExecutionKind     -- LOCAL_MANAGED | LOCAL_PASSTHROUGH | API
  execution_output : ExecutionOutput?  -- absent while IN_PROGRESS
  token_usage      : TokenUsage?       -- accounting; absent if not captured
  output_persisted : bool              -- fact: was the output stored to the blob store?
  -- future --
  trace            : ...               -- journal link, session, scope
```

**Lifecycle.** An execution exists *before* its result does:

1. On launch the execution is written to the database in `IN_PROGRESS`,
   carrying its identity.
2. The client runs and returns a result (stdout, stderr, exit code, files,
   usage).
3. If `output_persisted` is true, the output bytes are written to the blob
   store; structured fields are written to the database.
4. State is settled: `SUCCESS` or `FAILED`.

**`PASSTHROUGH` is not a state.** It is an `ExecutionKind` (see §3). A
`LOCAL_PASSTHROUGH` execution has the same `IN_PROGRESS → SUCCESS | FAILED`
lifecycle as any other; what differs is how much gmlcache manages (see §8).

**`output_persisted`** is a fact about this execution, not a policy. The policy
(`persist_output`) lives on the execution command (§8). An execution can
succeed but not persist its output — by explicit user choice — and it is still
a fully valid, journalled `MlExecution`.

---

## 3. Domain objects & value objects

### `CallIdentity`

The value object that determines the cache key. Holds only processed fields —
by the time it is constructed, every file path has been resolved to a content
fingerprint. It is not the user's raw request.

```
CallIdentity
  client                : str
  model                 : str
  effort                : str
  input_fingerprints    : Dict[str, str]   -- {absolute_path: sha256}
  client_args_fingerprint : str | None     -- sha256 of raw args; None if absent
  grants                : FrozenSet[str]   -- sorted, de-duplicated
```

Owns `generate_key() -> str` — a pure method that hashes only the in-memory
fields above. No I/O, no database access, no filesystem reads.

`allow_paths` (permission grant paths) are **not** a field on `CallIdentity`.
They do not enter the key (folder contents cannot be fingerprinted reliably).
They travel to the client runner via `ClientRunRequest` (§8).

### `ExecutionOutput`

The execution's heavy result. Opaque from the core's perspective; stored as
bytes by the blob store port.

```
ExecutionOutput
  stdout   : str
  stderr   : str
  exit_code : int
  files    : List[CapturedFile]
```

`TokenUsage` is **not** part of `ExecutionOutput`. Usage is mutable accounting
(database-bound, appended over time); it is a separate field on `MlExecution`.

### `TokenUsage`

Token and cost accounting. Not immutable output.

```
TokenUsage
  input_tokens        : int | None
  output_tokens       : int | None
  cache_read_tokens   : int | None
  cache_write_tokens  : int | None
  reasoning_tokens    : int | None
  reported_cost       : float | None   -- advisory; not authoritative billing
  raw_usage           : dict           -- preserved client block, verbatim
```

`None` means "not reported by this client", never zero.

### `CapturedFile`

A file produced inside the execution's isolated run folder and captured for
replay. Unchanged from current implementation.

### `ExecutionState`

```python
class ExecutionState(Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS     = "success"
    FAILED      = "failed"
```

### `ExecutionKind`

```python
class ExecutionKind(Enum):
    LOCAL_MANAGED     = "local_managed"
    LOCAL_PASSTHROUGH = "local_passthrough"
    API               = "api"
```

See §8 for what each kind means operationally.

---

## 4. The cassette — fully retired

The structured cassette file — a JSON document with named slots for stdout,
stderr, usage, and files — was **schema in a file**: a second schema in a
second technology, drifting from the authoritative database. That dissolves
entirely.

- There is no `Cassette` class.
- There is no `Cassette` file format.
- The blob store holds **opaque bytes** addressed by the key that
  `CallIdentity.generate_key()` produces.
- All structure (identity, state, cost, timestamps) lives in the database.

A stored blob has meaning only joined to its database row. The trade-off is
accepted: we lose open-one-file-and-read-everything inspectability in exchange
for a single authoritative schema and a trivially swappable blob store.

---

## 5. Persistence — the two layers

The dividing principle: **the database owns all structure; the blob store owns
only opaque bytes.**

**Database** — everything queryable, filterable, countable, relatable:
- execution identity (key, fingerprints)
- state, outcome, timestamps
- `output_persisted` flag
- token usage / cost
- call journal / event log (§6)
- session and scope links (future)
- hit-counts and stats — as **projections** over the journal, not stored truths

**Blob store** — opaque output bytes only:
- raw stdout, raw stderr, captured output files — bundled as opaque bytes,
  addressed by `CallIdentity.generate_key()`
- The store is **dumb**: `get(key) -> bytes | None`, `put(key, bytes) -> None`.
  It never parses a payload, never computes a key, never interprets content.

**Never store raw inputs.** Prompts, context, file contents are never
persisted. They exist in the system only as fingerprints in `CallIdentity`.
The identity is small and structured; it lives in the database.

---

## 6. The call journal / event log

Every call the system mediates produces events — asked, checked, hit/miss,
ran, stored, replayed — **whether or not output is stored**. This is the
event-sourced spine.

- **Events are the source of truth.** Hit-counts, token totals, session/cost
  views are projections over events, not stored truths.
- **Hit-counts do not live on `MlExecution`.** An immutable thing cannot count
  its own replays. Replay counts are journal data.
- A `LOCAL_PASSTHROUGH` execution that never stores its output still produces
  events; those events are the only record of its token cost.

---

## 7. Key generation & fingerprinting

Three distinct responsibilities, three distinct locations:

1. **File reading** — the use case reads the bytes at each declared path.
   This is I/O and belongs in the application layer (the use case calls a
   port, or reads directly at the inbound boundary). No file reading happens
   in the domain.

2. **Fingerprint rule** — `sha256` of file bytes. This rule is a **shared
   core function** (`common/checksum.py`) that every inbound path calls.
   A second front door (daemon, workflow engine library consumer) that
   reimplements this function could silently miss the cache. One rule,
   everywhere.

3. **Key generation** — `CallIdentity.generate_key()`. A pure method on the
   value object. It hashes the already-in-memory fingerprints. No I/O.

Summary: *reading* is the use case, the *rule* is core, *key generation* is
domain.

**Folder fingerprinting.** It is technically possible to compute a recursive
checksum of a directory (sort all paths, hash each file's bytes, combine into
one digest). This is expensive for large trees and the key changes on any file
change. Not implemented; `scan_trust` is the current lever. A future opt-in
`deep_fingerprint_paths` flag could offer this as an alternative.

---

## 8. Application inputs — three commands, three use cases

`Request` conflated three distinct concerns. The settled design separates them:

```
Native input (CLI args, daemon body)
  ↓ inbound adapter maps to →
ExecuteCommand  (raw user intent; no fingerprints)
  ↓ use case reads files, fingerprints, builds →
CallIdentity    (pure fingerprints; generate_key())
  ↓ use case builds →
ClientRunRequest  (what the client runner port receives)
```

The `ExecuteCommand` contains **raw user data only** — file paths, raw text,
flags. The use case is responsible for reading those files and computing
fingerprints. `CallIdentity` is constructed by the use case, never by the
command itself.

---

### Three commands and three use cases

#### `RunManagedLocalExecutionCommand` → `RunManagedLocalExecutionUseCase`

gmlcache takes full responsibility. Executes the client in an isolated
temporary folder. Detects generated files by comparing folder state before and
after. Manages grants. Computes fingerprints. Checks and updates the cache.

```
RunManagedLocalExecutionCommand
  client             : str
  model              : str
  effort             : str
  context            : str              -- raw text; fingerprinted by the use case
  prompt             : str              -- raw text; fingerprinted by the use case
  user_system_prompt : str | None       -- raw text; not keyed
  input_file_paths   : List[str]        -- raw paths; use case reads + fingerprints
  allow_paths        : List[str]        -- permission grant; NOT fingerprinted;
                                        --   signals client may scan these folders
  scan_trust         : bool             -- user asserts allow_paths won't invalidate;
                                        --   makes the call cacheable despite allow_paths
  client_args        : List[str]        -- raw passthrough args; fingerprinted by use case
  grants             : List[str]        -- capability names (net, read, write, …)
  cache_mode         : CacheMode        -- CACHE | OFFLINE | REFRESH
  persist_output     : bool             -- store output? default True
```

`allow_paths` does not enter the cache key. Its purpose is to tell the use
case to open the read-door for those folders when launching the client. By
default, declaring `allow_paths` makes the call non-cacheable (the cache
cannot fingerprint unbounded folder contents). `scan_trust = True` overrides
this: the user asserts responsibility and the call proceeds as cacheable.

#### `RunPassthroughExecutionCommand` → `RunPassthroughExecutionUseCase`

Thin wrapper. Everything after the adapter name is treated as opaque native
input and passed verbatim to the client. Executes in the caller's current
folder — no isolation, no grant management, no file capture. The user gets
caching of stdout/stderr/exit and usage tracking without gmlcache managing the
call.

```
RunPassthroughExecutionCommand
  client       : str          -- which adapter
  native_args  : List[str]    -- raw native arguments; opaque; enter the key as-is
  cache_mode   : CacheMode    -- CACHE | OFFLINE | REFRESH
  persist_output : bool       -- store output? default True
```

A `LOCAL_PASSTHROUGH` execution can be cached and replayed (for
stdout/stderr/exit). It cannot capture generated files because gmlcache has no
isolated folder to inspect.

#### `RunApiExecutionCommand` → `RunApiExecutionUseCase`

Direct API call to an ML provider. No local client executable. No filesystem
isolation, no grants, no allow-paths. The application builds the entire
context programmatically and sends it to the provider via `ApiClientPort`.

```
RunApiExecutionCommand
  provider       : str              -- which API provider
  model          : str
  messages       : List[Message]    -- full context, built by caller
  cache_mode     : CacheMode        -- CACHE | OFFLINE | REFRESH
  persist_output : bool             -- store output? default True
```

**Business rule: `persist_output = False` is incompatible with async execution
mode** (future §OPEN). An async execution must be stored — the caller retrieves
the result by ID at a later time and the stored output is the only source.

---

### `ClientRunRequest`

The DTO the use case constructs and passes to `ClientRunnerPort`. It carries
only what the client runner needs to launch the client. The command's
gmlcache-specific policy fields (`cache_mode`, `persist_output`, `scan_trust`)
do not travel here.

```
ClientRunRequest
  client             : str
  model              : str
  effort             : str
  context            : str
  prompt             : str
  user_system_prompt : str | None
  allow_paths        : List[str]
  client_args        : List[str]
  grants             : FrozenSet[str]
```

---

## 9. Ports

### Outbound (owned by core, implemented in adapter layer, dumb)

**`ClientRunnerPort`** — launch a local ML client executable, return the
result. The adapter knows the specific CLI; the core does not.

```python
class ClientRunnerPort(ABC):
    @abstractmethod
    def run(self, request: ClientRunRequest) -> ExecutionOutput: ...
```

**`ApiClientPort`** — call an ML provider API directly. Separate port from
`ClientRunnerPort` because the contract is fundamentally different (no
subprocess, no filesystem, no grants). An initial `StubApiClientAdapter` in
`adapter/out/api/` supports testing before a real adapter exists.

```python
class ApiClientPort(ABC):
    @abstractmethod
    def call(self, request: RunApiExecutionCommand) -> ExecutionOutput: ...
```

**`BlobStorePort`** — store and retrieve opaque output bytes by key.

```python
class BlobStorePort(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes | None: ...
    @abstractmethod
    def put(self, key: str, output: bytes) -> None: ...
```

**`MetricsPort`** — append journal events; query projections for reporting.

```python
class MetricsPort(ABC):
    @abstractmethod
    def record_event(self, event: str, **fields) -> None: ...
    @abstractmethod
    def last_access(self) -> Dict[str, float]: ...
```

### Inbound (the use-case contracts)

One inbound port per use case. Each names the action and declares the command
type it accepts. Defined in `application/port/inbound/`.

---

## 10. Engine model and project split

### The engine is stateless

The execution engine (the use-case layer) has no mutable state between calls.
Each call is independent: it receives its collaborators through constructor
injection and processes one command at a time. A daemon (future inbound
adapter) is stateful — it manages connections, sessions, and live-status
subscriptions — but the engine it wraps is not.

### Project split

The project will be split into two independently installable packages:

- **`generic-ml-cache-core`** — the hexagonal application: domain model, use
  cases, port contracts, `common/`. Contains zero knowledge of any client
  implementation or daemon. A consuming project (e.g.
  `generic-ml-workflow`) depends on this package, provides its own port
  implementations, and injects them. No adapter code, no CLI, no
  subprocess invocation.

- **`generic-ml-cache-cli`** (or `generic-ml-cache`) — the CLI inbound adapter
  and all current outbound adapters (local client runner, filesystem blob store,
  SQLite metrics store). Depends on `core`.

All placement decisions made now must be compatible with this split. The rule:
if it would belong in `core`, it must never import from what will become
`cli`. The architectural boundary that enforces hexagonal correctness today is
the same boundary the package split will formalise tomorrow.

---

## 11. Principles carried (the durable rulings)

- **Caching ≠ metrics — two independent concerns.** `persist_output = False`
  suppresses blob storage. It does not suppress the call journal. A call that
  stores nothing still logs its events, token cost, and session link. Only a
  separate explicit "no-trace" decision would suppress logging.
- **`allow_paths` is a permission grant, not a key element.** Its purpose is
  to open the read-door for the ML client. Non-cacheability is a consequence
  (folder contents cannot be fingerprinted), not the intent. `scan_trust`
  overrides the cacheability consequence; it does not change the grant.
- **The store stays dumb.** Intelligence (keys, rules, fingerprint logic) lives
  in the core. A store translates a key to its own address and reads/writes
  bytes. Nothing else.
- **Configuration is injected, never imposed.** The core receives its
  collaborators through constructors. It never reads a config file or selects
  a datasource.

---

## 12. Naming — all settled

| Old name | Settled name | Location |
|---|---|---|
| `Request` | `CallIdentity` | `application/domain/model/call_identity.py` |
| `Response` | `ExecutionOutput` | `application/domain/model/execution_output.py` |
| `Usage` | `TokenUsage` | `application/domain/model/token_usage.py` |
| `Cassette` | *(retired)* | — |
| `Outcome` | *(retired — facts live on `MlExecution`)* | — |
| `ClientStatus` | *(retired — replaced by `ExecutionState`)* | — |
| `Mode` | `CacheMode` | `application/domain/model/cache_mode.py` |
| `match_key()` | `generate_key()` on `CallIdentity` | |
| — | `MlExecution` | `application/domain/model/ml_execution.py` |
| — | `ExecutionState` | `application/domain/model/execution_state.py` |
| — | `ExecutionKind` | `application/domain/model/execution_kind.py` |
| — | `ClientRunRequest` | `application/domain/model/client_run_request.py` |
| — | `BlobStorePort` | `application/port/out/blob_store_port.py` |
| — | `MetricsPort` | `application/port/out/metrics_port.py` |
| — | `ApiClientPort` | `application/port/out/api_client_port.py` |

**OPEN (future work, not blocking current build):**

- Async execution mode and its command. Constraint already recorded: async
  requires `persist_output = True`.
- Scope and session objects and their port contracts (roadmap 1.1–1.2).
- The exact event vocabulary of `MetricsPort.record_event`.
- Whether `deep_fingerprint_paths` (recursive folder checksum) becomes a
  supported field on `RunManagedLocalExecutionCommand`.
- On a cache hit: return a full `MlExecution` reconstructed from storage, or
  return `ExecutionOutput` only? Leaning: reconstruct an `MlExecution` so the
  aggregate is always the thing returned, but exact implementation is open.

---

## 13. Relationship to AGENTS.md

This document defines the **objects**; `AGENTS.md` defines the **rules** they
are built by. Examples of the handshake:

- AGENTS §6 "logic lives on the domain object" → `generate_key` is on
  `CallIdentity`, not on a store or service.
- AGENTS §5 "no schema on disk / dumb ports" → `BlobStorePort` is
  `get/put` by key; all structure is database-only.
- AGENTS §11 "parse at the edge" → the use case reads files and fingerprints
  them before building `CallIdentity`; raw paths never reach the domain.
- AGENTS §5 "core depends only inward" → the project split (§10) is the
  physical enforcement of this rule: `core` has no adapter imports by
  construction.

When an OPEN item above is settled, it is recorded here first, and if it
introduces an enforceable rule, also in `AGENTS.md`.
