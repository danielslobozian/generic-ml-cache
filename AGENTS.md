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

This is a hexagonal application. The **core** (the `application/` layers) depends on
nothing outward and contains the business rules. The aggregate is an **ML
execution** — a demand to run a client and what came back. Around the core sit
**ports** (interfaces the core owns) and **adapters** (implementations, outside the
core). Structure is database; bytes are filesystem: the database owns everything
queryable (an execution's identity, cost, outcome, event log), the filesystem owns
only opaque output blobs addressed by key. Inbound adapters (terminal, later a
daemon) map their native input into a command and call a use case; outbound adapters
(client runner, blob store, metrics store) are dumb and swappable. Place new code by
asking which ring it belongs to and letting the dependency direction decide.

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
p = self._root / f"{k}.json"
data = client.run(req)

# RIGHT — the referent and role are in the name
cassette_path = self._root / f"{execution_key}.json"
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
ring.

```
application/domain/model/     domain objects & value objects — the nouns the
                              system is about (execution, call-identity, result,
                              usage). Pure. No I/O, no framework, no adapters.
application/domain/service/   domain services — pure rules that span objects.
application/usecase/          use cases — orchestration; each names an action and
                              takes a command as input.
application/port/in/          inbound port contracts (the use-case interfaces).
application/port/out/         outbound port contracts (store, metrics, client
                              runner) — owned by the core.
adapter/in/...                inbound adapters (terminal, daemon) — map native
                              input to a command, call a use case. OUTSIDE the core.
adapter/out/...               outbound adapters (client, blob storage, metrics db)
                              — implement an out-port. OUTSIDE the core. Dumb.
common/                       genuinely cross-cutting leaves (errors, checksums).
```

Note: `in` is a Python keyword, so an inbound package directory cannot be literally
named `in`; use `inbound` (or the agreed concrete name) while keeping the `port/in`
*concept*.

## 5. Layer & dependency discipline (the invariants)

These are hard architectural lines. A change that crosses one is wrong even if it
passes every test.

- **The core depends only inward.** `application/` imports nothing from `adapter/`.
  Dependencies point toward the domain; never outward.
- **Ports are owned by the core.** The interface lives in `application/port/...`;
  the implementation lives in `adapter/...`. The core names the contract and depends
  on the contract, never on the concrete adapter.
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
- **Configuration is injected, never imposed.** The core receives its collaborators
  and config through constructors; it never reads a config file or chooses a
  datasource. The composition root (an inbound adapter, or a consuming application)
  builds the concrete adapters and hands them in.

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
  into an outbound port DTO. That is the use case's own job (it alone knows both
  boundaries) and it *cannot* move onto either object: the command is an inbound-port
  type and the DTO is a domain type, so neither may depend on the other.
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

Pure, dependency-free logic has exactly two homes, **neither of which is a use case**:
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
  (The key→filename mapping lives in a single `_path_for`, not inline in every
  method that needs it.)
- No duplicated string literals (`S1192` — hoist to a named constant), no
  copy-pasted blocks, no dead or commented-out code (`S125`), no unused
  imports / variables / parameters (`S1481`/`S1172`/`S1128`).

## 9. Control flow

- **Guard clauses over buried conditionals.** Test the exceptional case first and
  return early; keep the main path unindented. Do not bury the condition inside an
  inline conditional expression when a guard reads clearer.
- **Compose, don't branch.** Replace `if/elif` ladders that select behaviour with
  injected strategy objects where the ladder will grow.

```python
# WRONG — main path buried, condition hidden
return Cassette.from_json(path.read_text()) if path.exists() else None

# RIGHT — guard first, main path plain
if not path.exists():
    return None
return Cassette.from_json(path.read_text())
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
- This file evolves with the project. When a new structural decision is made, it is
  recorded here as an enforceable line with its failing case, so the standard and
  the code never drift.
