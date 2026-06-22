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

The project began as a **cache**: store a *record* (inputs, key, outputs), and on a
matching input, replay it. As it grew — direct client calls, streaming, events,
token/session statistics, execution types that deliberately do not store output —
that stored record stopped being the thing the system is *about*.

The tell: a `LOCAL_PASSTHROUGH` execution (one that runs but stores no output) has no
stored record, yet is unmistakably a real thing — it has inputs, it ran, it produced
output, it cost tokens. If the stored record were the aggregate, that call would be
nothing. It is obviously *something*.

**Decision: the aggregate is `MlExecution`.** The earlier framing — a stored record as
the aggregate — is fully retired (see §4).

---

## 2. The aggregate — `MlExecution`

An `MlExecution` is a demand to run an ML client and what came back. It is the
aggregate root.

```
MlExecution
  call_identity    : CallIdentity        -- the value object that determines the key
  execution_state  : ExecutionState      -- IN_PROGRESS | SUCCESS | FAILED (the run)
  execution_kind   : ExecutionKind       -- LOCAL_MANAGED | LOCAL_PASSTHROUGH | API
  artifacts        : List[Artifact]      -- the output, unified (stdout/stderr/files)
  token_usage      : TokenUsage?         -- accounting; absent if not captured
  failure          : ExecutionFailure?   -- the cause; present only when FAILED
  output_persisted : bool                -- fact: was the output stored to the blob store?
  superseded_at    : timestamp?          -- cache currency: null = current; set = stale
  -- future --
  trace            : ...                 -- journal link, session, scope
```

The output is a **list of `Artifact`s** (§3), not a separate `ExecutionOutput`
object — stdout, stderr, and each generated file are each one artifact. There is
no top-level `exit_code`: a success carries none (success means "all good"), and
a failure's exit code is one detail of its `failure` (§3), which also covers
API-mode causes that have no exit code at all.

**Lifecycle.** An execution exists *before* its result does:

1. On launch the execution is written to the database in `IN_PROGRESS`,
   carrying its identity.
2. The client runs; the runner returns a `ClientRunResult` (§9) — raw exit code,
   stdout, stderr, generated files. Nothing is stored yet.
3. The use case turns each raw piece into a stored `Artifact` (hash → `blob.put`
   → `blob_key`); if `output_persisted` is true the bytes land in the blob store
   and the structured record in the database.
4. State is settled: `SUCCESS`, or `FAILED` with an `ExecutionFailure`.

**`PASSTHROUGH` is not a state.** It is an `ExecutionKind` (see §3). A
`LOCAL_PASSTHROUGH` execution has the same `IN_PROGRESS → SUCCESS | FAILED`
lifecycle as any other; what differs is how much gmlcache manages (see §8).

**`output_persisted`** is a fact about this execution, not a policy. The policy
(`persistence_depth`) lives on the execution command (§8). An execution can
succeed but not persist its output — at `METER` depth, by explicit user choice —
and it is still a fully valid, journalled `MlExecution`.

**Executions are append-only; refresh never destroys.** A `call_identity` (one
key) has **many** executions over time — each row is one real client call.
`ExecutionState` is the **run** axis (`IN_PROGRESS | SUCCESS | FAILED`: how the
call ended). `superseded_at` is a **separate cache-currency axis** (is this
still the authoritative answer): null = current, set = stale. The two never
conflate — a stale execution was a success; staleness only marks it as no longer
in use.

- **Current answer** = `state == SUCCESS AND superseded_at IS NULL AND
  output_persisted`. At most one per key at a time.
- **Refresh** creates a *new* `IN_PROGRESS` execution and leaves the old current
  one untouched and still serving. Only at the **atomic instant the new run
  succeeds** do old and new flip in a single transaction (old gets
  `superseded_at`, new becomes current). If the new run **fails**, the old stays
  current and keeps answering — no good value is ever destroyed for a failed
  refresh.
- A concurrent cache-mode reader during a refresh sees the old row, still
  `SUCCESS + current`, so it always gets a consistent value — never a half-state.
- This also yields the count distinction for free: **real client calls** for a
  key = its execution rows; **cache requests** = journal events; **served from
  cache** = hit events.

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

**Input-file keying is path-sensitive (a soundness ruling).** Both the file's
path *and* its content fingerprint enter the key. A rename (same content, new
name) therefore yields a **new key → a miss → a re-run**, never a hit. This is
deliberate: the prompt may reference a declared file by name, so a rename can
change the real result — keying on content alone would be a false-positive hit,
which the prime directive ("sound replay over hit-rate; prefer a miss to a wrong
hit") forbids. The case where a rename *should* be transparent (a prompt that
globs `rule*.md`) is the `allow_paths` / `scan_trust` mechanism, not this one:
globbing needs folder access, which is non-cacheable unless the user explicitly
trusts the folder. Granularity: the path is the user's declared path resolved to
absolute (most conservative); a portable/relative-keying mode can be an opt-in
later if a shared cache makes machine-specific keys a problem.

`allow_paths` (permission grant paths) are **not** a field on `CallIdentity`.
They do not enter the key (folder contents cannot be fingerprinted reliably).
They travel to the client runner via `ClientRunRequest` (§8).

### `Artifact`

One generated document of an execution's output. stdout, stderr, and each output
file are each an `Artifact`. An artifact is a **stored** thing — it always has a
`blob_key` (the content checksum addressing its bytes in the blob store). Its
`content` is materialised only when hydrated; dehydrated, only the reference
remains.

```
ArtifactType : STDOUT | STDERR | OUTPUT_FILE      -- (RAW_USAGE later)

Artifact  (frozen)
  artifact_type : ArtifactType
  name          : str | None    -- relative path for OUTPUT_FILE; None for stdout/stderr
  encoding      : str           -- utf-8 | binary
  blob_key      : str           -- content checksum; always present (an artifact is stored)
  size_bytes    : int
  content       : bytes | None  -- materialised when hydrated; None when dehydrated
```

`Artifact` replaces the old `ExecutionOutput` (retired) and subsumes
`CapturedFile`. `TokenUsage` is **not** an artifact — it is accounting, a
separate field on `MlExecution`.

### `ClientRunResult`

The **transient, raw** result the `ClientRunnerPort` returns — the contract
surface of the runner port, not an adapter-internal type. It carries what the
client produced, before anything is hashed or stored. The **use case** turns it
into stored `Artifact`s (it owns the blob storage; the runner never touches the
blob store).

```
GeneratedFile  (frozen)
  name    : str
  content : bytes

ClientRunResult  (frozen)
  exit_code : int
  stdout    : str
  stderr    : str
  files     : List[GeneratedFile]
```

### `ExecutionFailure`

The interpreted cause of a failed run — present only when `state == FAILED`.
Separate from stderr (which is captured output, an `Artifact`): this is *why* it
failed. It generalises across local and API executions.

```
FailureReason : NONZERO_EXIT    -- (TIMEOUT | NETWORK | CLIENT_ERROR … as features land)

ExecutionFailure  (frozen)
  reason    : FailureReason
  message   : str            -- the client/API's own error text
  exit_code : int | None     -- the local client's exit code when that's the cause; None for API
```

Exit code lives here, not on `MlExecution`: it only carries meaning on failure,
and it is one cause among several (a future timeout or network drop has no exit
code). API failures use a `reason` + `message` with no exit code.

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

## 4. No on-disk record schema

An earlier design stored each result as a structured file — a JSON document with named
slots for stdout, stderr, usage, and files. That was **schema in a file**: a second
schema in a second technology, drifting from the authoritative database. It dissolves
entirely.

- There is no per-result file format, and no class for one.
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

**Blob store** — opaque artifact bytes only:
- Each artifact is its own blob: **stdout, stderr, each output file, and the raw
  usage document** are separate blobs. The database holds one `artifacts`
  metadata row per artifact (type, name, checksum, size, encoding).
- The blob is **content-addressed**: its key is the artifact's *own* content
  checksum (`file_content_fingerprint` of its bytes), not the execution key.
  This gives free deduplication (identical output across runs is stored once)
  and free integrity.
- The store is **dumb**: `get(key) -> bytes | None`, `put(key, bytes) -> None`,
  `remove(key) -> None`. It never parses a payload, never computes a key, never
  interprets content.

**Content-addressed blobs are shared, so deletion is reference-counted.** One
blob may be referenced by many executions (two pipelines that produce the same
answer share one blob). A blob is removed **only when no `artifacts` row still
references its `blob_key`** — the `artifacts` table is the reference index.
Because executions are append-only, a *refresh deletes nothing synchronously*;
cleanup is a separate, reference-counted prune that removes a blob only when its
last referencing execution is gone. The ref-count check spans the repository
(artifacts) and the blob store (bytes), so the GC orchestration lives in a
**prune use case**, never inside either port.

**Normalized vs raw usage.** The normalized token counts (input/output/cache/
reasoning/cost) are queryable → database columns. The **raw** usage block is
client-specific and its shape varies per client and per API, so it is not forced
into a schema — it is an artifact of type `raw_usage`, stored as opaque bytes.

**Never store raw inputs.** Prompts, context, file contents are never
persisted. They exist in the system only as fingerprints in `CallIdentity`.
The identity is small and structured; it lives in the database.

### Reference schema (the SQLite adapter's internal concern)

The core only ever sees the ports and domain objects; this relational shape is
owned by the persistence *adapter* and informs the port contract and the
aggregate's hydrate/dehydrate behaviour. It will evolve.

```
call_identities             -- the keyed "call": the user's choices, as fingerprints
  id PK; execution_key TEXT UNIQUE (generate_key()); client; model; effort;
  context_fingerprint; prompt_fingerprint; client_args_fingerprint NULL;
  package_inputs INTEGER (future)
call_identity_input_files   -- {path: fingerprint} map, one row each
  call_identity_id FK; path; fingerprint
call_identity_grants        -- the grant set, one row each
  call_identity_id FK; grant_name

executions                  -- the aggregate root; APPEND-ONLY (many per call_identity)
  id PK; call_identity_id FK; kind; state; exit_code NULL;
  output_persisted INTEGER; superseded_at TEXT NULL; created_at; updated_at;
  session_id FK NULL (future)
artifacts                   -- one row per stored artifact; bytes live in the blob store
  id PK; execution_id FK; type (stdout|stderr|output_file|raw_usage);
  name NULL; encoding; blob_key (content checksum); size_bytes; created_at
token_usage                 -- normalized accounting, 1:1 with execution
  execution_id FK UNIQUE; input_tokens NULL; output_tokens NULL;
  cache_read_tokens NULL; cache_write_tokens NULL; reasoning_tokens NULL;
  reported_cost NULL
events                      -- the call journal (today's access_registry, folded in later)
  id PK; ts; event; execution_key NULL; client; model; effort; session_id NULL

scopes / sessions           -- future (roadmap 0.3 / 0.4)
```

**Hydrate / dehydrate.** The repository stores and returns a *dehydrated*
`MlExecution`: the structured row + call identity + **artifact metadata** +
normalized usage, with **no bytes** (`execution_output is None`). The use case
*hydrates* it by fetching each artifact's bytes from the blob store and
reassembling `ExecutionOutput`. So the repository deals in structure, the blob
store deals in bytes, and the **use case bridges them** — the two ports never
call each other.

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

## 7. Key generation, fingerprinting, and input transparency

**Transparency stance.** The engine reads as little of the user's input as it
can, and persists none of it raw. Declared input files are fingerprinted *at
the filesystem edge* — their content never enters the engine — and only the
checksum is ever stored. Context and prompt are different: the user types them
into the command, so they necessarily pass through the engine to reach the
client; but they too are persisted only as fingerprints, never as raw text.

Four distinct responsibilities, four distinct locations:

1. **File reading + hashing (input files)** — happens inside the
   `FileFingerprintPort` adapter. The adapter reads the bytes at a declared
   path, applies the imported core rule, and returns **only the checksum**. The
   content never crosses back into the use case or the domain. This is how the
   engine fingerprints a file without ever holding its content.

2. **The fingerprint rule** — `file_content_fingerprint(bytes) -> str`
   (`common/checksum.py`), the `sha256` of the raw bytes. It is a **fixed core
   function the adapter imports directly — never injected as a parameter.**
   Injection would let two front doors (CLI, daemon, library consumer) supply
   two different rules and silently miss each other's cache. A direct import
   makes divergence *impossible* (a hard line), not merely discouraged
   (a convention one can rationalise around). One rule, everywhere.

3. **Context / prompt fingerprinting** — these already live in the command
   (the user typed them), so the use case hashes them in place with the shared
   `text_checksum` rule. No extra exposure: the engine already holds them.

4. **Key generation** — `CallIdentity.generate_key()`. A pure domain method
   that hashes the already-in-memory fingerprints. No I/O.

Summary: *file reading + file hashing* is the fingerprint adapter (content
stays at the edge), the *rule* is a directly-imported core function,
*context/prompt hashing* is the use case, *key generation* is the domain.

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
  package_inputs     : bool             -- opt-in (default False): aggregate declared
                                        --   files' content into the structured context;
                                        --   elides file-read grants; keyed (see below)
  cache_mode         : CacheMode        -- CACHE | OFFLINE | REFRESH
  persistence_depth  : PersistenceDepth -- METER | CACHE | DATASET; default CACHE
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
  cache_mode        : CacheMode        -- CACHE | OFFLINE | REFRESH
  persistence_depth : PersistenceDepth -- METER | CACHE | DATASET; default CACHE
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
  cache_mode        : CacheMode        -- CACHE | OFFLINE | REFRESH
  persistence_depth : PersistenceDepth -- METER | CACHE | DATASET; default CACHE
```

**Business rule: the `METER` depth (storing no output) is incompatible with async
execution mode** (future §OPEN). An async execution must be stored — the caller
retrieves the result by ID at a later time and the stored output is the only source.

---

### Context packaging (optional feature; specified here, built later)

Context is modelled as a **structured object**, of which the user's raw context
is one key's value. An opt-in capability, `package_inputs`, aggregates each
declared input file — `{name, path, checksum, content}` — into that structure.

- **Local managed mode:** optional. When enabled, the file content rides inside
  the context, so the client no longer needs file-read grants — making a local
  run a faithful stand-in for an API run for comparison.
- **API mode:** always on. The API cannot read disk, so packaging is the only
  path for file content to reach the model.
- The engine **never inspects the context**, so it cannot and will not detect
  if the user *also* placed the same content there by hand. That is the user's
  responsibility — a direct consequence of the transparency stance (§7).
- Packaging is the one path where the engine reads file *content* (through an
  explicit content-read capability, distinct from `FileFingerprintPort`). Even
  then, only the checksum is persisted — never the content.

**Packaging is part of the call identity.** A packaged run and a non-packaged
run of the same files are different invocations — different actual model input,
different grants — and must **never reuse each other's result**. Reusing across
modes would be unsound *and* would defeat the comparison the feature exists for.
It follows the established "absent → nothing added to the key" pattern:
packaging **off** contributes nothing (today's keys unchanged), packaging **on**
adds a marker (its own distinct key). File fingerprints stay in the key in both
modes. There is no `scan_trust`-style override here — distinct by default, full
stop.

---

### `ClientRunRequest`

The DTO the use case constructs and passes to `ClientRunnerPort`. It carries
only what the client runner needs to launch the client. The command's
gmlcache-specific policy fields (`cache_mode`, `persistence_depth`, `scan_trust`)
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
    def run(self, request: ClientRunRequest) -> ClientRunResult: ...
```

The runner returns a **raw** `ClientRunResult` (§3) — it never hashes, never
computes a key, never stores. The use case turns that result into stored
`Artifact`s and persists them.

**`ApiClientPort`** — call an ML provider API directly. Separate port from
`ClientRunnerPort` because the contract is fundamentally different (no
subprocess, no filesystem, no grants). An initial `StubApiClientAdapter` in
`adapter/out/api/` supports testing before a real adapter exists.

```python
class ApiClientPort(ABC):
    @abstractmethod
    def call(self, request: RunApiExecutionCommand) -> ClientRunResult: ...
```

Like the client runner, the API adapter returns a raw `ClientRunResult` (with no
exit code / a synthetic one, and the response body as stdout); the use case
stores it. (Its exact shape is settled when the API use case is built.)

**`BlobStorePort`** — store and retrieve opaque output bytes by key.

```python
class BlobStorePort(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes | None: ...
    @abstractmethod
    def put(self, key: str, output: bytes) -> None: ...
    @abstractmethod
    def remove(self, key: str) -> None: ...   # used by reference-counted prune (§5)
```

**`MetricsPort`** — append journal events; query projections for reporting.

```python
class MetricsPort(ABC):
    @abstractmethod
    def record_event(self, event: str, **fields) -> None: ...
    @abstractmethod
    def last_access(self) -> Dict[str, float]: ...
```

**`FileFingerprintPort`** — fingerprint a declared input file *at the edge*.
The adapter reads the file and applies the imported core rule, returning only
the checksum; the content never enters the engine (§7).

```python
class FileFingerprintPort(ABC):
    @abstractmethod
    def fingerprint(self, path: str) -> str: ...
```

**`ExecutionRepositoryPort`** — the "database": store and retrieve the
structured execution record (state, kind, token_usage, output_persisted,
timestamps) keyed by `generate_key()`. It holds **no** output bytes (the blob
store's job) and **no** journal events (the metrics port's job). On a hit the
use case reads the structured record here *and*, when `output_persisted`, the
output bytes from the blob store, then assembles the `MlExecution`.

```python
class ExecutionRepositoryPort(ABC):
    @abstractmethod
    def find_current(self, execution_key: str) -> MlExecution | None: ...   # the cache lookup: current success, dehydrated
    @abstractmethod
    def save(self, execution: MlExecution) -> None: ...    # append a new execution; if SUCCESS, atomically supersede the prior current
```

`find_current` returns the dehydrated current answer (`state == SUCCESS`,
`superseded_at` null, `output_persisted`); the use case hydrates it from the
blob store. `save` appends a new execution and, when that execution is a
success, atomically supersedes the prior current one — the supersession
transaction lives inside the adapter, where atomicity belongs.

**Datasources are injected from the inbound side (§10).** The composition root
builds the concrete repository / blob / metrics / fingerprint adapters — which
folder, which database file — and hands them to the use case through its
constructor. The core names only the ports; it never chooses a datasource.

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

**Constructor injection is the default shape of every component.** Each use
case and each adapter is a class that receives its collaborators — ports,
datasources, config — through its constructor; it never reaches out for them.
The **composition root owns lifecycle**: a terminal client builds the adapters,
makes one call, and throws them away (stateless); a daemon or other stateful
host builds them once and holds them in memory across calls (stateful). The
components are identical in both cases — only the root differs. This is exactly
what lets one core serve a one-shot CLI and a long-lived daemon unchanged.

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

- **Caching ≠ metrics — two independent concerns.** The `METER` depth suppresses
  blob storage. It does not suppress the call journal. A call that stores nothing
  still logs its events, token cost, and session link. Only a separate explicit
  "no-trace" decision would suppress logging.
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
- **The engine reads no input content it does not have to.** Declared files are
  fingerprinted at the edge — content never enters the engine — and context and
  prompt pass through only because the user typed them; even they are persisted
  only as fingerprints. The engine reads file *content* solely when the user
  explicitly enables packaging (§8), and even then stores only the checksum.

---

## 12. Naming — all settled

| Old name | Settled name | Location |
|---|---|---|
| `Request` | `CallIdentity` | `application/domain/model/call_identity.py` |
| `Response` | *(retired — replaced by `Artifact` + `ClientRunResult`)* | — |
| `Usage` | `TokenUsage` | `application/domain/model/token_usage.py` |
| `Cassette` | *(retired)* | — |
| `Outcome` | *(retired — facts live on `MlExecution`)* | — |
| `Mode` | `CacheMode` | `application/domain/model/cache_mode.py` |
| `match_key()` | `generate_key()` on `CallIdentity` | |
| — | `MlExecution` | `application/domain/model/ml_execution.py` |
| — | `ExecutionState` | `application/domain/model/execution_state.py` |
| — | `ExecutionKind` | `application/domain/model/execution_kind.py` |
| — | `Artifact` / `ArtifactType` | `application/domain/model/artifact.py` |
| — | `ExecutionFailure` / `FailureReason` | `application/domain/model/execution_failure.py` |
| — | `ClientRunResult` / `GeneratedFile` | `application/domain/model/client_run_result.py` |
| — | `ClientRunRequest` | `application/domain/model/client_run_request.py` |
| — | `file_content_fingerprint()` | `common/checksum.py` |
| — | `BlobStorePort` | `application/port/out/blob_store_port.py` |
| — | `MetricsPort` | `application/port/out/metrics_port.py` |
| — | `ClientRunnerPort` | `application/port/out/client_runner_port.py` |
| — | `FileFingerprintPort` | `application/port/out/file_fingerprint_port.py` |
| — | `ExecutionRepositoryPort` | `application/port/out/execution_repository_port.py` |
| — | `ClockPort` / `SystemClock` | `application/port/out/clock_port.py` |
| — | `ApiClientPort` | `application/port/out/api_client_port.py` |
| `ExecutionOutput` | *(retired mid-refactor — superseded by `Artifact`)* | — |

`ClientStatus` is **kept** (discovery / `doctor` output — unrelated to the
execution aggregate; an earlier draft wrongly listed it for retirement).

**OPEN (future work, not blocking current build):**

- Async execution mode and its command. Constraint already recorded: async
  requires at least `CACHE` depth (it must store its output).
- Scope and session objects and their port contracts (roadmap 0.5 / 0.7).
- The exact event vocabulary of `MetricsPort.record_event`.
- Whether `deep_fingerprint_paths` (recursive folder checksum) becomes a
  supported field on `RunManagedLocalExecutionCommand`.
- On a cache hit: the use case reconstructs (hydrates) a full `MlExecution` from
  the dehydrated repository record plus the blob bytes. Settled in principle; the
  exact hydration helper is built with the managed-local use case.

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
