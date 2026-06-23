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

Each use case is **three files in two homes**, following the ports-and-adapters
convention:

- `port/inbound/<action>_use_case.py` → **`<Action>UseCase`** — the inbound port,
  an `ABC` with the single `execute(command) -> <Result>` method. The driving
  adapter depends on *this*, never on the implementation.
- `port/inbound/<action>_command.py` → **`<Action>Command`** — the command. It is
  part of the inbound contract (the port method takes it), so it lives with the
  port, **not** with the implementation.
- `usecase/<action>_service.py` → **`<Action>Service`** — the implementation,
  which subclasses the port. This is the orchestration.

So the interface carries the `UseCase` name and the implementation carries
`Service`. The failing case: a concrete class named `<Action>UseCase` in
`usecase/` with no interface above it is wrong — the name belongs to the port,
and the driving adapter has nothing to depend on but the concrete class.

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
  calls — is **deleted**, not retained "just in case". A `vulture`/coverage flag is
  right until proven otherwise.
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
- **Ports are explicit `ABC`s** with `@abstractmethod`. An adapter declares the port
  it implements by subclassing it (the nominal "implements"); a half-built adapter
  fails to instantiate. (Prefer `ABC` over `Protocol` here: the explicit declaration
  and the runtime refusal are wanted.)
- **Ship `py.typed`.** The package publishes its types so consumers (a daemon, the
  workflow engine) get them.

---

## Using this document

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
- **Green means both linters.** A change is not green until `ruff check` **and**
  `ruff format --check` both pass — formatting is part of the floor, and CI runs both.
  Running only `ruff check` is a partial check, not a pass.
- This file evolves with the project. When a new structural decision is made, it is
  recorded here as an enforceable line with its failing case, so the standard and
  the code never drift.
