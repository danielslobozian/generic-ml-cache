<div align="center">

# Storage

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

## At a glance

- [Authority](#authority)
- [The execution store](#the-execution-store)
- [The blob store](#the-blob-store)
- [The access registry](#the-access-registry)
- [Eviction](#eviction)
- [Future scope-aware storage](#future-scope-aware-storage)
- [Scope invalidation](#scope-invalidation)

---

gmlcache separates **structure** from **bytes**. The structure of every execution — its
identity, kind, outcome, usage, and the references to its output — lives in a database.
The output bytes live in a content-addressed blob store. A third, non-load-bearing
database records access events for reporting.

The current store is local and lives in a per-user data directory by default (the
caller chooses it; there is no baked-in location). A simplified layout:

```text
<store>/
  executions.sqlite3      # the execution repository — structured records
  blobs/                  # content-addressed output bytes (stdout, stderr, files)
  registry.sqlite3        # the access registry — events & hit counts (non-load-bearing)
```

## Authority

The **database is authoritative** for relationships and metadata. The filesystem layout
of the blob store is an implementation detail: bytes are addressed by their content key,
not by a folder name. A folder name is never proof of ownership, authorization, or
correctness, and the blob layout may be reorganized later (filesystem ↔ S3 ↔ memory)
without touching the engine.

## The execution store

The **execution repository** (SQLite) holds the structured record of every execution:

- its **call identity** — denormalized query columns (kind, client, model, effort) plus
  the full identity serialized as JSON, so polymorphic identities (managed, passthrough,
  API) coexist without collision and without raw prompts or context ever being stored;
- the **kind** and **state** (success / failed) and any **failure** detail;
- the **artifacts** — for each output (stdout, stderr, a generated file): its type, size,
  and the **blob key** that locates its bytes (the bytes themselves are not in the
  database);
- the **token usage** when reported;
- bookkeeping: when it was created, and `superseded_at`.

Records are **append-only**. A refresh records a *new* execution and atomically marks the
prior one superseded on success; a failed refresh leaves the existing success untouched.
Only a current, successful, persisted execution answers a cache hit.

## The blob store

Output bytes — stdout, stderr, and any generated files — live in a **content-addressed
blob store**: each blob is keyed by the checksum of its bytes, so identical content is
stored exactly once and shared across executions that produced it. An execution's
artifacts reference blobs by key; deleting an execution removes a blob only when no other
artifact references it. The store is a dumb port (`BlobStorePort`): it translates a key to
its own address and reads/writes bytes — it never computes keys or interprets payloads.

## The access registry

The registry records access events — `hit`, `miss`, `record` — and powers:

- `stats`,
- hit counts in `list`.

It is **not load-bearing for correctness**: if registry data is missing, the execution
store still defines exactly what was recorded and what a hit replays. It is deliberately
separate from the executions, which stay pure.

## Eviction

Size-based eviction is **planned, not yet implemented**. The `max_size` configuration key
is reserved for it but is not enforced today, and there is no background scheduler. See
the [roadmap](ROADMAP.md).

## Future scope-aware storage

Future scopes may introduce additional metadata and possibly additional physical
organization. The likely model is:

```text
Scope
  owns Sessions
  references Executions

Session
  observes Executions
```

A public scope may be available when no scope token is supplied. Private scopes selected
by scope token may reuse public executions according to policy, but that relationship
should be metadata-driven rather than inferred from folder paths.

## Scope invalidation

Future scope-token invalidation should be treated as storage cleanup.

Invalidating a scope token means deleting or orphaning that scope's metadata, sessions,
and scope-owned execution references. It is not a login revocation operation and should
not be documented as authentication.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
