# AGENTS.md

The standard any code added to this project must meet — whether written by an AI
agent or a human. It is the contract code is **generated against** and **reviewed
against**.

One principle governs every rule below:

> **A rule must be enforceable.** If a violation can be rationalised as compliant,
> the rule is too soft and is rewritten as a hard line with its failing case shown.

These rules are the **bar**. Static analysis (Sonar) is the **floor** — the
mechanical minimum. Where this document and the floor overlap, this document is
stricter and wins. Several rules here are things Sonar *cannot* see (whether a name
is meaningful, whether logic sits in the right layer); those are the ones that need
a generating agent and a reviewer to hold the line.

The reasoning behind much of this is the body of work on software craftsmanship —
Robert C. Martin's *Clean Code*, McConnell's *Code Complete*, the hexagonal /
ports-and-adapters pattern. This file is not a summary of those; it is the subset
this project enforces, made concrete.

---

## The project in one paragraph (context for placement)

This is a hexagonal application shipped as a **monorepo of two package rings**: the
**library** (`packages/core`, `generic_ml_cache_core`) and the **clients**
(`packages/cli` today, a daemon later). The **library is the whole application
*except* the user interface and the data source**: it contains the hexagon's
`application/` rings (domain, use cases, ports — the business rules, depending on
nothing outward), **and the default outbound adapters** (`adapter/out/...`: client
runner, blob store, SQLite repository, metrics), **and** the composition factory that
wires them. The aggregate is an **ML execution** — a demand to run a client and what
came back. A **client** is thin: it provides the data source and configuration and
maps its native surface (a terminal, later a REST API) onto the library's public API.
Structure is database; bytes are filesystem: the database owns everything queryable
(an execution's identity, cost, outcome, event log), the filesystem owns only opaque
output blobs addressed by key. Mind two distinct boundaries: the **ring** boundary —
inside the library, `application/` imports nothing from `adapter/` — and the
**package** boundary — a client imports the library; the library imports no client.
Place new code by asking which ring *and which package* it belongs to, and letting
the dependency direction decide.

---

# Family A — Naming

## 1. Variable names

A name states **what specifically** the value is, not **what kind** of thing it is.
The type is already in the type; the name must add the referent and the role.

- **No abbreviations. No single-letter names. In any binding.** Locals, parameters,
  loop variables, comprehension targets — all held to the same bar. This is
  mechanical; there is no case where `p`, `s`, `idx`, `tmp`, `cfg`, `e`, `n` is
  acceptable.
- **The name answers "of what?"** A name that only restates the type (`path`,
  `data`, `result`, `text`, `value`, `item`, `obj`) is a non-name — it is a type
  wearing a longer coat, and it is as much a defect as a single letter.

```python
# WRONG — type-names and abbreviations; the reader still has to ask "of what?"
p = self._root / f"{k}.bin"
data = client.run(req)

# RIGHT — the referent and role are in the name
blob_path = self._root / f"{blob_key}.bin"
client_result = client.run(execution_command)
```

Disinformation is also banned: do not name a value for something it is not (a
mapping named `…_list`, a count named `…_flag`). The name and the thing must agree.

## 2. Method names

A method name is the **clear intent of the action**: a verb and its object. A method
*does* something; its name says what.

- Actions get verbs: `generate_key`, `persist_output`, `record_event`,
  `load_execution`. Never a noun for an action (`match_key` names a thing, not the
  act of producing it — it is `generate_key`).
- A query that returns a value without side effects reads as the question it
  answers: `is_cacheable`, `has_grant`. Honour command/query separation — a method
  either does something or answers something, not both.
- Vague verbs (`process`, `handle`, `manage`, `do`) are not intents. State the real
  action.

```python
# WRONG
def match_key(self): ...        # a noun; what does it DO?
def process(self, x): ...       # process what, into what?

# RIGHT
def generate_key(self) -> str: ...
def persist_output(self, execution_key: str, output: ClientOutput) -> None: ...
```

---

# Family B — Structure & placement (the hexagon)

This family is the heart of the standard and the most project-specific. Sonar does
not enforce any of it.

## 3. Code separation — what lives in its own file

- **One class per file.** A module holds one class (plus the small free functions
  that serve only it). The filename is the snake_case of the class.
- **Data is separated from behaviour at the file level.** A value object / DTO and
  the service that acts on it do not share a file.
- **A port and its adapter never share a file**, and never share a layer (see §4).
  The interface lives with the core; the implementation lives outside it.
- A cohesive family may stay together where splitting would scatter meaning (e.g. a
  single exception hierarchy in one module). This is the only exception, and it is
  about cohesion, not convenience.

## 4. Code positioning — which folder holds what

The hexagon is the map. Every new file has exactly one correct home; place it by
ring *and* package.

```
packages/core/   THE LIBRARY (generic_ml_cache_core) — everything but the UI & the data source
  application/domain/model/    domain objects & value objects — the nouns the
                               system is about (execution, call-identity, result,
                               usage). Pure. No I/O, no framework, no adapters.
                               Related value objects are grouped into named
                               subpackages (e.g. `purge/` holds `PurgeReport`
                               and related retention types).
  application/domain/service/  domain services — pure rules that span objects.
  application/usecase/         use cases — orchestration; each names an action and
                               takes a command as input.
  application/port/inbound/    inbound port contracts (the use-case interfaces).
  application/port/out/        outbound port contracts (store, metrics, client
                               runner) — owned by the core ring.
  adapter/out/...              the DEFAULT outbound adapters (client runner, blob
                               store, SQLite repository, metrics) — implementations
                               that SHIP with the library. Dumb, swappable.
  adapter/inbound/             the composition factory (build_use_cases): wires the
                               default adapters around an injected data source.
  common/                      cross-cutting leaves (errors, checksums, coercion).

packages/cli/    A CLIENT (generic_ml_cache_cli) — the thin terminal UI
  cli.py                       argparse, output formatting, exit codes.
  config.py                    the INI config reader (a client concern).
  __main__.py                  the entry point.
                               Depends on the library; supplies the data source and
                               config; maps terminal commands onto the public API.
```

Note: `in` is a Python keyword, so an inbound package directory cannot be literally
named `in`; use `inbound` while keeping the `port/in` *concept*. The driving inbound
adapter (the terminal UI) is a separate **client package**, not a folder under the
library's `adapter/`; the library's `adapter/inbound/` holds only the wiring factory.

### The use-case triple (inbound naming, settled)

**Every user-driven capability is an inbound port** — defined by the *boundary*
it sits on (a CLI command, a daemon route reaching it), not by the number of
implementations. Each capability lives in a **by-capability sub-package** so its
ports and commands stay together:

- `port/inbound/<capability>/<action>_use_case.py` → **`<Action>UseCase`** — the
  inbound port, an `ABC`. A single-method use case (one operation, its command,
  its result). The driving adapter depends on *this*, never the implementation.
- `port/inbound/<capability>/<action>_command.py` → **`<Action>Command`** — the
  command, part of the inbound contract (the port method takes it), so it lives
  with the port, **not** with the implementation. (No command for a no-input
  query.)
- `usecase/<capability>_service.py` → **`<Capability>Service`** — the
  implementation. A capability with several operations regroups its single-method
  use cases into **one** service implementing all their ABCs, each as a
  **distinctly-named method** (e.g. `SessionTagsService.tag` / `.untag` /
  `.list_tags`). The single-operation form (run/probe/gateway) keeps the
  `execute(command)` method name.

So the interface carries the `UseCase` name and the implementation carries
`Service`. A **mere option is a command field, not a new use case** (`hard` is
`PurgeByTagCommand(tag, hard=False)`, never a `HardDeleteByTagUseCase`) — the
command is the evolution seam. The **discriminator-in-one-method** form (one
`execute` switching on a target/type tag) is **forbidden** — it is the if/elif
ladder §9 forbids. *Failing cases: a concrete `<Action>UseCase` in `usecase/`
with no interface above it; dropping a new `*_use_case.py` into a flat `inbound/`
once the capability has a sub-package; omitting a `PurgeUseCase` because
`PurgeService` has one implementation.*

**The genuine exception — a purely-internal service.** A service invoked only by
other use cases or the composition root, *never reachable by a driving adapter*,
gets no inbound port — regardless of its implementation count. Note the inverse
is NOT a reason to omit a port: a primary port characteristically has exactly
**one** implementation (the application service itself), and it still gets a
port. The boundary is the test, not the count. The capability services are
exposed to controllers only through the narrowed `ApplicationApi` bundle (§5);
the composition root keeps the out-adapters and injects them into the impls.

> **The core exposes inbound ports to the outside, never implementations.**
> Everything a driving adapter can invoke from outside the application is an
> **inbound port** — an `ABC` in `port/inbound/`, reached through the
> `ApplicationApi` bundle. A `*Service` implementation is never exposed across the
> boundary; it is wired behind its ports in the composition root and reached only
> as the port type. This holds for *every* capability without exception — breadth
> of surface or a single implementation is **not** a licence to skip the ports
> (purge has many operations and one implementation, and it still gets a full set
> of per-operation `*UseCase` ABCs + command DTOs, exactly like every other
> capability). *Failing case: a controller importing or being handed a concrete
> `…Service` instead of its inbound port — the implementation has leaked across
> the boundary the ports exist to seal.*

### The base-use-case hook (post-record side effects)

`CachedMlExecutionService` is the abstract base for all recording use cases.
It exposes a `_after_record(execution_key: str) -> None` template-method hook
called immediately after every successful execution record. Override it in a
concrete subclass when a post-record side effect is needed (quota eviction,
indexing, notification).

- **Post-record side effects belong here**, not scattered inline across multiple
  implementations.
- The hook receives only the key of the just-recorded execution.
- **The hook must not raise.** A side-effect failure must not roll back or
  obscure a successful record. Swallow and log, never propagate.
- The base implementation is a silent no-op; subclasses opt in by overriding.

```python
# WRONG — post-record side effect inlined in the concrete service
class RunMlExecutionService(CachedMlExecutionService):
    def execute(self, command):
        key = super().execute(command)
        self._purge_service.evict_to_quota(self._max_size)  # wrong place
        return key

# RIGHT — side effect isolated in the hook; base class calls it at the right moment
class RunMlExecutionService(CachedMlExecutionService):
    def _after_record(self, execution_key: str) -> None:
        if self._max_size:
            self._purge_service.evict_to_quota(self._max_size)
```

## 5. Layer & dependency discipline (the invariants)

These are hard architectural lines. A change that crosses one is wrong even if it
passes every test.

- **The core ring depends only inward.** `application/` imports nothing from
  `adapter/`. Dependencies point toward the domain; never outward. (This is the
  *ring* boundary; it holds *inside the library* — which contains both rings.)
- **The package boundary: the library ships the adapters; a client never reimplements
  them.** The library (`packages/core`) depends on nothing in the repo; a client
  (`packages/cli`, a daemon) depends on the library; **the library imports no client.**
  The library is the whole application minus the UI and the data source, so it ships
  the default outbound adapters — a consumer reuses them by *injecting a data source*,
  never by rewriting them. This is the Spring Batch model: the framework ships the
  writers; you provide the `DataSource`. *Failing case: a `SqliteExecutionRepository`
  (or any adapter) placed in `packages/cli`, forcing an embedding application to
  re-implement it — that defeats the point of the library.*
- **Ports are owned by the core ring.** The interface lives in `application/port/...`;
  the implementation lives in `adapter/...` (still inside the library). The core ring
  names the contract and depends on the contract, never on the concrete adapter.
- **Driving adapters reach the application only through inbound ports.** A
  controller (a CLI command, a daemon route) invokes the domain ONLY via the
  inbound ports handed to it in the `ApplicationApi` bundle — which carries inbound
  ports *only* (no `blob_store`/`repository`/`metrics`/`diag`). It must not import a
  use-case implementation, an outbound port, or a domain service; an outbound
  adapter is unreachable from a controller by construction. Enforced by import-linter
  Rule 10 (`hex-controllers-inbound-only`) + the narrowed bundle. *Failing case: a
  controller calling `wired.repository.find(...)` instead of an
  `execution_query.find_current(...)` inbound port.*
- **No I/O in the domain.** Domain objects and domain services read no files, open
  no sockets, touch no database. I/O is an adapter concern. (A domain object may
  compute over data it already holds — e.g. generate a key from in-memory
  fingerprints — but it must never *fetch* that data.)
- **No schema on disk.** The database owns all structure (anything queryable). The
  filesystem stores only opaque bytes addressed by key. A file with named, parsed
  fields is a database in the wrong place — it is a defect.
- **Outbound adapters are dumb.** The engine supplies the key and the rules; a store
  translates that key to its own address and persists. A store never computes keys,
  never knows the hashing rule, never interprets payloads. This is what keeps it
  swappable (filesystem ↔ S3 ↔ memory).
- **Configuration is injected, never imposed; the library is stateless and holds no
  *location*.** The library receives its collaborators and config through constructors;
  it never reads a config file or chooses a datasource. What is **baked in** is
  *structure* — table names, the on-disk blob naming, the schema by which data is
  retrieved. What is **injected** is every *location* — the store path, the database
  path, the blob root — and any config. A hardcoded path, a default store directory, or
  a config-file read *inside the library* is a defect. A client (or a consuming
  application) owns config, locations, and any process state (threads, a scheduler);
  the composition root hands the wired adapters in. *Failing case: the library
  defaulting its own store directory instead of receiving it.*

```python
# WRONG — domain reaches outward and parses a stored schema
class Execution:
    def load_output(self, path):           # domain doing I/O
        return json.loads(path.read_text()) # and parsing on-disk schema

# RIGHT — domain pure; the engine asks a dumb port for bytes by key
class BlobStorePort(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes | None: ...
```

## 6. Logic placement (domain-driven)

Behaviour lives **on the object whose data it concerns**, not leaked into a service
or an adapter. If the inputs to a computation all live on one domain object, the
computation is a method on that object.

- Key generation belongs on the execution/call-identity that owns the fields, not in
  the store that happens to need it. The store asks for a key; it does not make one.
- A use case orchestrates (decides *what* happens in *what order*); it delegates the
  *rules* to the domain and the *I/O* to ports. A use case that contains business
  rules has absorbed something that belongs in the domain.

### The static-method tell (the hard line)

The rule above is too easy to rationalise ("it's just a small helper"), so it gets a
mechanical detector. **Orchestration is methods that use the injected ports.** A method
on a use case that touches *neither `self` nor a port* — in Python, anything you can
mark `@staticmethod` — is therefore **not orchestration**: it computes a value purely
from domain or command fields, which makes it a **rule**, and a rule belongs on the
object whose data it reads.

- **A `@staticmethod` on a use case / service is a defect by default. Move it to the
  domain object that owns the data it reasons over.**
- **The one allowed exception: a boundary mapping** — translating the inbound command
  into an outbound port's request DTO. Mediating between the inbound and outbound
  boundaries is the use case's *defining* job. The mapping must not move onto the
  inbound command: that would make the inbound shape know an outbound port's contract —
  the precise coupling the use case exists to absorb. So this one self-less method
  stays in the service.
- **More than that one mapping is an alarm.** Two or more static methods on a use case
  means rules have leaked into the orchestrator — stop and re-analyse before going on.

```python
# WRONG — a rule living in the use case (no self, no port): domain logic, wrong layer.
class RunManagedLocalExecutionService:
    @staticmethod
    def _interpret(result: ClientRunResult) -> ExecutionState:
        return ExecutionState.FAILED if result.exit_code else ExecutionState.SUCCESS

# RIGHT — the rule sits on the object that owns the field it reads.
class ClientRunResult:
    def outcome(self) -> ExecutionState:
        return ExecutionState.FAILED if self.exit_code else ExecutionState.SUCCESS
```

Pure logic has exactly two homes, **neither of which is a use case**:
a method on the domain value object whose fields it computes over, or — when it belongs
to no single object — a module-level function in `common/`. A `@staticmethod` on a use
case or service is neither, and is the signal to relocate.

---

# Family C — Code-quality floor (anticipate Sonar; clear it on the first write)

These overlap with Sonar's defaults. Generated code must clear them up front, so the
gate never has to send it back.

## 7. Method size & complexity

A function does **one thing**. The mechanical ceilings (Sonar defaults, treated as
hard limits):

- **Cognitive complexity ≤ 15** (Sonar `S3776`). Deep nesting is penalised hardest —
  prefer extraction and early return.
- **Nesting depth ≤ 4** (`S134`); **return statements ≤ 3** (`S1142`);
  **parameters ≤ 7** (`S107`) — more than a handful means a parameter object /
  command is missing; **function length** kept short (`S138`).

When a function approaches a ceiling the fix is **extract a well-named method**, not
a comment that announces sections.

## 8. Reusability / no duplication

- A value or expression built in more than one place becomes **one named method**.
  (The key→path mapping lives in a single `_path_for`, not inline in every
  method that needs it.)
- No duplicated string literals (`S1192` — hoist to a named constant), no
  copy-pasted blocks, no dead or commented-out code (`S125`), no unused
  imports / variables / parameters (`S1481`/`S1172`/`S1128`).

### No code for unbuilt futures (YAGNI) — but know a skeleton from a relic

- Dead code includes code kept *"for later"*: a symbol with **zero callers** — a
  method, a constant for an unbuilt feature, a "kept for compatibility" seam nobody
  calls — is **deleted**, not retained "just in case". A zero-coverage symbol (one
  no test ever reaches) is suspect until proven otherwise. (Static dead-code scanners
  were tried and dropped: a ports/entry-point/DI architecture reads as "unused" to
  them, so they flag the seams that make the design work — false positives unfit to
  gate CI.)
- The line is **callers + a plan**, not *real vs stub*. A **stubbed but
  wired-and-tested** implementation of a committed seam (a placeholder adapter the
  composition root injects and the suite drives end-to-end) is a *walking skeleton*,
  not dead code. A symbol with no caller **and** no plan is a *relic*.
  - *Relic (delete): an `EVICT` event constant for an eviction feature that does not
    exist — no implementation, no caller, no test.*
  - *Skeleton (keep): a stub API-client adapter the use case and tests drive while the
    real provider adapter is pending — **provided the API run kind is actually on the
    roadmap, not aspirational.** If the seam is not committed, it is a relic too.*

### A removed concept leaves no trace

- When a feature or concept is removed, its **vocabulary** is removed with it — not
  just its code. After removal, a search for the concept's name returns **nothing**:
  no identifiers, no comments, no docstrings, no help text, no docs (this file
  included). A lingering name is disinformation (§1). *Failing case: a record format
  is deleted, yet variables still named for it, comments describing it, and a help
  string mentioning it survive — a grep for the retired name still lights up.*
  - **The one exception is the `CHANGELOG`'s history.** A released version's entry is
    a factual record of what shipped; if a past release had the feature, its entry
    legitimately names it. Scope the grep to live code, docs, and *forward-looking*
    changelog sections — never rewrite shipped entries to erase a retired name.

## 9. Control flow

- **Guard clauses over buried conditionals.** Test the exceptional case first and
  return early; keep the main path unindented. Do not bury the condition inside an
  inline conditional expression when a guard reads clearer.
- **Compose, don't branch.** Replace `if/elif` ladders that select behaviour with
  injected strategy objects where the ladder will grow.

```python
# WRONG — main path buried, condition hidden
return blob_path.read_bytes() if blob_path.exists() else None

# RIGHT — guard first, main path plain
if not blob_path.exists():
    return None
return blob_path.read_bytes()
```

## 10. Error handling

- **A real, cause-named exception hierarchy.** Raise specific exceptions that name
  the cause; never raise or catch bare `Exception`/`BaseException` (`S112`) except
  at a deliberate, commented best-effort boundary.
- **Translate foreign errors at the adapter boundary** into the project's own
  exception vocabulary. The core never leaks a library's exception type.
- **Fail loud in the core.** The engine verifies (a declared output exists, a key
  matches) rather than trusting; a broken assumption raises, it does not pass
  silently.

## 11. Typing & contracts

- **Parse at the edge.** Untyped external input (CLI args, JSON, client stdout) is
  converted into typed objects **once, at the adapter boundary**; the core then
  trusts the types. Dicts of loose strings do not travel into the domain.
- **Ports are explicit `ABC`s with `@abstractmethod` — by default.** An adapter
  declares the port it implements by subclassing it (the nominal "implements"); a
  half-built adapter fails to instantiate. The explicit declaration and the runtime
  refusal are the point. **`Protocol` is allowed only when the type is structural by
  intent** — a structural supertype narrowed at runtime, or a structural shape over
  domain/command objects that must not inherit a port. *The test: does/should the
  implementor write `class X(ThePort)`? Yes ⇒ ABC; satisfied incidentally ⇒
  Protocol.* When an adapter provides a port's surface by **composition** rather than
  by defining the methods itself (e.g. a CLI client adapter that delegates
  `LocalClientPort` to a composed `CliRuntime`), it still subclasses the ABC through a
  thin delegating base (`ComposedLocalClient`) so the nominal "implements" — and the
  fail-to-instantiate guarantee — hold; composition is *how* the methods are provided,
  not a reason to drop to a Protocol. *Failing case: a `LocalClientPort` that adapters
  only match structurally while its sibling `MlRunnerPort` is an ABC they subclass —
  the two driven-client ports must enforce conformance the same way.* The only
  remaining `Protocol`s are the three genuinely-structural ones: `RegisteredAdapterPort`
  (a structural supertype narrowed at runtime), `CacheableExecutionCommand`, and
  `KeyedCallInputs` (structural shapes over command/identity objects).
- **Frozen objects are deeply immutable.** `@dataclass(frozen=True)` freezes only the
  attribute *bindings*; a `list`/`dict`/`set` field is still mutable in place, so the
  object is only shallowly immutable — a soundness hole for a cache identity or a
  command that is keyed on. A frozen object's collection fields are therefore
  immutable: `tuple[...]` / `frozenset[...]` / `Mapping` backed by `MappingProxyType`,
  normalized in `__post_init__` (`object.__setattr__`), accepting any iterable input at
  the boundary. Nested structures are **deep-frozen** via `common/immutable.deep_freeze`
  — notably `GatewayRequest.body`, which the gateway both keys on and forwards: a mutable
  body opens a TOCTOU gap between keyed/recorded and forwarded, and one frozen snapshot
  guarantees keyed ≡ forwarded ≡ recorded. The rare code that must JSON-serialize a
  frozen structure thaws it once at that boundary (`common/immutable.thaw`;
  `MappingProxyType` is not `json`-serializable). *Failing case: a `@dataclass(frozen=True)`
  with a bare `list`/`dict`/`set` field — shallow immutability on a cache identity or
  command object is a defect.*
- **Ship `py.typed`.** The package publishes its types so consumers (a daemon, the
  workflow engine) get them.

---

## Using this document

- **Read this file before writing any code.** An agent that skips this step will
  violate rules that are clearly stated here, as happened with the dual-linter
  requirement in 0.11.0 — the rule existed; it simply was not read.
- New code is generated to clear every rule above on the first write — not to be
  corrected toward it afterward.
- Review against it rule by rule. A respectable-looking violation (`path`, a noun
  method name, a rule in the wrong layer) is still a violation; the test is the one
  at the top — *could this be rationalised as compliant?* If yes, it is a defect and
  the rule gets tightened here so it cannot be next time.
- **Show, don't assert.** A claim that something is *removed, clean, done, or passing*
  is demonstrated, never asserted — a grep that returns nothing, a green test run, a
  tool report. "I removed all of X" without the search that proves it is how a stray
  name from a deleted feature survives. Evidence first, claim second.
- **Green means both linters and all coverage gates.** A change is not green until
  all seven checks pass:
  1. `ruff check packages/`
  2. `ruff format --check packages/`
  3. `python -m pytest packages/core/tests   --cov=generic_ml_cache_core   --cov-fail-under=80 --cov-report=xml:packages/core/coverage.xml`
  4. `python -m pytest packages/cli/tests    --cov=generic_ml_cache_cli    --cov-fail-under=80 --cov-report=xml:packages/cli/coverage.xml`
  5. `python -m pytest packages/daemon/tests --cov=generic_ml_cache_daemon --cov-fail-under=80 --cov-report=xml:packages/daemon/coverage.xml`
  6. `lint-imports` — enforces the four hexagonal import contracts in `.importlinter`:
     application ring must not import adapters; driver packages must not reach past the
     composition root into `adapter.out`; domain model must not import use cases;
     driven adapter sub-packages must not import each other. A BROKEN contract is an
     architecture defect, not a style issue.
  7. `pyright` — static type checking (standard mode) against `pyrightconfig.json`.
     Zero errors required. `# type: ignore` is acceptable only for provably safe casts
     that cannot be expressed in the type system; a comment must be present explaining
     why (e.g. `# type: ignore[arg-type]  # settings dict values are object`).

  Gates 6 and 7 also run automatically as **pre-commit hooks** (`.pre-commit-config.yaml`).
  After cloning, run `.venv/bin/pre-commit install` once to wire them into `git commit`.
  A commit that breaks either contract is then rejected before it enters local history.

  Running only the linters, or skipping coverage, is a partial check, not a pass.
  The XMLs produced by (3), (4), and (5) are the exact files Sonar ingests — running
  them locally shows the number Sonar will report before any push.

  **Local Sonar scan** — reproduce the full Sonar gate before pushing:

  ```bash
  # 1. Generate the three coverage XMLs (already gitignored via coverage.xml in .gitignore)
  python -m pytest packages/core/tests   --cov=generic_ml_cache_core   --cov-report=xml:packages/core/coverage.xml
  python -m pytest packages/cli/tests    --cov=generic_ml_cache_cli    --cov-report=xml:packages/cli/coverage.xml
  python -m pytest packages/daemon/tests --cov=generic_ml_cache_daemon --cov-report=xml:packages/daemon/coverage.xml

  # 2. Run the scanner (mounts the repo root; finds the XMLs via sonar-project.properties)
  docker run --rm \
    -e SONAR_TOKEN \
    -v "$(pwd):/usr/src" \
    sonarsource/sonar-scanner-cli
  ```

  The XMLs are written inside the repo tree so the Docker mount (`$(pwd):/usr/src`)
  makes them visible to the scanner at the paths declared in `sonar-project.properties`.
  They are not committed — `.gitignore` excludes `coverage.xml` at every depth.
- **No AI attribution in commits or pull requests.** Commit messages and PR
  titles/bodies must never contain any reference to the AI tool that produced them.
  Specifically forbidden:
  - `Co-Authored-By: Claude …` or any other `Co-Authored-By` trailer pointing to an AI
  - Footers or lines of the form `Generated with Claude Code`, `🤖 Generated with …`,
    or any equivalent self-identification phrase
  - Any mention of the AI assistant's name in the commit subject or body
  The commit and PR history must read as if written by the human author.
  *Failing case: a PR body ending with `🤖 Generated with [Claude Code](…)` — that
  line must be absent.*
- **Never work directly on `main`.** Every change — no matter how small — is made on
  a dedicated branch. Branch naming:
  - `feature/<scope>` — user-facing capability
  - `tech/<scope>` — internal refactor, tooling, or build change
  - `fix/<scope>` — bug fix
  - `release/<version>` — version bump + changelog only (no code)
  - `docs/<scope>` — documentation only
  Create the branch before touching any file. `main` is only ever updated via a merged
  PR. An agent that edits files while on `main` has violated this rule; the correct
  recovery is `git checkout -b <branch>` immediately (staged changes carry over).
- **Version and release documentation are release-branch-only.** `VERSION`,
  `CHANGELOG.md`, and `docs/ROADMAP.md` must never be touched on a `feature/`,
  `tech/`, `fix/`, or `docs/` branch. They are only modified on a `release/<version>`
  branch, and only after the feature work for that version has been implemented and
  already merged into `main`. An agent that edits these files on any other branch has
  violated this rule and must immediately revert those changes.
  *Failing case: bumping VERSION or writing a CHANGELOG entry on a feature branch
  before the implementation PR is even merged — the release commit arrives before the
  code it describes.*
- **Release branch checklist.** A release branch commit must touch exactly three files —
  no more, no less. A PR diff that omits any of the three is wrong and must not merge:
  1. `VERSION` — bumped to the new version string.
  2. `CHANGELOG.md` — the `[Unreleased]` section replaced with `[X.Y.Z] - YYYY-MM-DD`
     and the release notes written under it.
  3. `docs/ROADMAP.md` — the milestone heading for the released version gains
     `*(released YYYY-MM-DD)*` appended after the title.
  *Failing case: a release PR that updates `VERSION` and `CHANGELOG.md` but leaves the
  roadmap milestone without a release date — the roadmap then silently misrepresents the
  milestone as unshipped.*
- This file evolves with the project. When a new structural decision is made, it is
  recorded here as an enforceable line with its failing case, so the standard and
  the code never drift.
