<div align="center">

# Storage

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

## At a glance

- [Authority](#authority)
- [Current cassette layout](#current-cassette-layout)
- [Registry](#registry)
- [Current eviction](#current-eviction)
- [Future scope-aware storage](#future-scope-aware-storage)
- [Scope invalidation](#scope-invalidation)

---

gmlcache stores immutable cassettes and non-load-bearing registry data.

The current store is local and filesystem-backed. Cassettes are JSON files. The
access registry is SQLite. The database and filesystem serve different purposes:

- **cassettes** hold recorded execution results,
- **registry data** holds access events, hit counts, eviction ordering, and future
  scope/session/reporting metadata,
- **folders** are a useful representation and organization mechanism, not a
  security boundary.

## Authority

The database is the authoritative place for relationships and metadata.

The filesystem layout is an implementation detail. It may be flat, grouped by
scope, grouped by object type, or reorganized later. A folder name should not be
treated as proof of ownership, authorization, or correctness.

## Current cassette layout

Today cassettes are stored as JSON files named by their match key. A simplified
example:

```text
<cassette-store>/
  <match-key>.json
  registry.sqlite3
```

The key is derived from the execution request. The file content contains the
recorded request identity, response, generated files, schema version, and usage
metadata.

## Registry

The registry records events such as:

- hit,
- miss,
- record,
- evict.

The registry supports:

- `stats`,
- hit counts in `list`,
- LRU-style eviction ordering,
- future scope/session reporting.

The registry is not load-bearing for correctness. If registry data is missing or
unavailable, the cassette format still defines what was recorded.

## Current eviction

Current eviction is optional and size-based.

When `max_size` is configured, the store evicts least-recently-used cassettes on
insertion to make room for a new cassette. LRU ordering uses last access from the
registry, falling back to file metadata when needed.

The new cassette is never evicted by the insertion it caused. The cap is therefore
a soft cap: a single large cassette may exceed it.

There is no background scheduler for current size eviction.

See [Cache eviction](concepts/cache-eviction.md).

## Future scope-aware storage

Future scopes may introduce additional metadata and possibly additional physical
organization. The likely model is:

```text
Scope
  owns Sessions
  references Cassettes

Session
  observes Executions

Execution
  records or reuses a Cassette
```

A public scope may be available when no scope token is supplied. Private scopes
selected by scope token may reuse public cassettes according to policy, but that
relationship should be metadata-driven rather than inferred from folder paths.

## Scope invalidation

Future scope-token invalidation should be treated as storage cleanup.

Invalidating a scope token means deleting or orphaning that scope’s metadata,
sessions, and scope-owned cassette references. It is not a login revocation
operation and should not be documented as authentication.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
