<div align="center">

# Cache Eviction

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Current implementation: size-based LRU eviction](#current-implementation-size-based-lru-eviction)
- [Soft cap](#soft-cap)
- [Current configuration](#current-configuration)
- [Time-based eviction](#time-based-eviction)
- [Scope-aware eviction](#scope-aware-eviction)
- [Scope token invalidation](#scope-token-invalidation)

---

Cache eviction controls storage growth. It does not decide whether a cassette is
correct.

## Current implementation: size-based LRU eviction

Today gmlcache supports optional size-based eviction.

When `max_size` is configured, inserting a new cassette may evict older cassettes
until the store has room. The eviction order is least-recently-used.

Freshness is based on last access, not creation time.

For example:

- a cassette created one month ago but replayed one hour ago is fresh,
- a cassette created two days ago but not touched since yesterday is less fresh.

This is enforced on insertion. No daemon or scheduler is required.

## Soft cap

The configured max size is a soft cap.

The cassette being inserted is never evicted by the insertion that created it. If
a single cassette is larger than the configured cap, the store may exceed the cap.

## Current configuration

`max_size` can be configured through the normal configuration path. It is off by
default.

## Time-based eviction

Time-based eviction is different.

A rule such as “remove cassettes stale for more than 30 days” requires periodic
cleanup or an explicit maintenance command. That belongs to future retention work
or daemon/resident-service behavior.

## Scope-aware eviction

Future scope tokens introduce new retention questions:

- global max size,
- per-scope max size,
- public-scope retention,
- private-scope retention,
- scope invalidation,
- session cleanup.

Scope-aware eviction should be metadata-driven. Folder layout may help humans see
what exists, but the database should remain authoritative.

## Scope token invalidation

Invalidating a scope token should remove the scope’s cached data and metadata.

It is not an authentication revocation flow. It is a cache cleanup operation.

A future invalidation operation should define what happens to:

- scope-owned cassette references,
- sessions,
- execution events,
- usage summaries,
- copied or shared public cassette references.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
