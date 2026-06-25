<div align="center">

# Retention and quota

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [What retention means](#what-retention-means)
- [Store size](#store-size)
- [Size quota and LRU eviction](#size-quota-and-lru-eviction)
- [Soft purge vs hard delete](#soft-purge-vs-hard-delete)
- [The purge command](#the-purge-command)
- [What survives a soft purge](#what-survives-a-soft-purge)
- [Practical advice](#practical-advice)

---

gmlcache keeps every recorded execution until you remove it or a quota forces eviction.
There is no automatic time-based expiry — entries persist until you act.

## What retention means

Every execution you record accumulates on disk: its output blob (and input blob at `dataset`
depth), the execution record in SQLite, token usage, tags, and access events. Nothing is
removed automatically unless a size quota is configured. Over time this lets you replay any
past call and report on the full history of token spend — but the store grows without bound
unless you manage it.

## Store size

`gmlcache stats` reports the total store size on disk. Blob storage is the dominant
contributor; SQLite metadata is negligible.

When `max_size` is configured the output also shows the fill level:

```text
store size : 3.2 MB / 5.0 GB (64%)
```

The fill percentage is teal when below 80% of quota and amber at 80% or above.
`--json` adds `"store_bytes"` and `"max_size_bytes"` (or `null` when no quota is set).

## Size quota and LRU eviction

Set a storage quota in the config file or via the environment variable:

```ini
# config file
max_size = 5GB
```

```bash
# environment
export GMLCACHE_MAX_SIZE=500MB
```

Accepted suffixes: `GB`, `MB`, `KB` (case-insensitive). After each new execution is
recorded, if the total store size exceeds the quota, gmlcache soft-purges the
least-recently-accessed executions in LRU order until the store is at or below quota.

LRU order is derived from the access journal — the log of every cache hit and inspection.
Executions that have never been accessed since they were recorded fall back to their
creation timestamp. Eviction is automatic and silent; `gmlcache stats` reflects the
result immediately.

> [!NOTE]
> LRU eviction is a **soft purge** — blobs are freed and artifact rows are removed, but
> execution records, token usage, tags, and access events are kept. Statistics survive
> eviction. See [Soft purge vs hard delete](#soft-purge-vs-hard-delete) below.

## Soft purge vs hard delete

| | Soft purge (default) | Hard delete (`--hard`) |
|---|---|---|
| Blobs freed | Yes | Yes |
| Artifact rows removed | Yes | Yes |
| `output_persisted` cleared | Yes | N/A — row is removed |
| Execution record kept | Yes | No |
| Token usage kept | Yes | No |
| Tags kept | Yes | No |
| Access events kept | Yes | No |
| Statistics survive | Yes | No |

Use soft purge to reclaim disk space while keeping the "what happened" history.
Use hard delete when you want the executions gone entirely — nothing survives.

## The purge command

`gmlcache purge` removes executions by one of four target selectors (mutually exclusive):

| Selector | Scope |
|---|---|
| `gmlcache purge <key>` | One execution identified by its cache key (or short prefix) |
| `gmlcache purge --tag <tag>` | All executions carrying this tag |
| `gmlcache purge --session <id>` | All executions from this session |
| `gmlcache purge --all` | Every execution in the store |

Append `--hard` to any of the above for a hard delete instead of a soft purge.

`--all` is guarded by a required confirmation phrase to prevent accidents:

```bash
gmlcache purge --all --confirm "purge all"             # soft-purge everything
gmlcache purge --all --hard --confirm "hard delete all" # hard-delete everything
```

`--json` emits a machine-readable summary:

```json
{"executions_removed": 12, "bytes_freed": 3355443, "blobs_removed": 12}
```

## What survives a soft purge

After a soft purge, the stored bytes are gone but the record of the execution remains:

- **Token usage** — input and output token counts, used for `session report` and `stats`
- **Cache hit counts** — how many times an entry was replayed
- **Session history** — invocation events that placed this execution in a session
- **Execution tags** — labels attached at record time

The stored prompts, outputs, and inputs (the actual bytes) are freed. The entry can no
longer be replayed — a subsequent cache miss will call the model live.

## Practical advice

**Free space, keep history.** Soft purge by tag to reclaim disk for a category of
executions while leaving their usage statistics intact for reporting.

**Clean slate.** Hard-delete with `--all` when you want to start fresh — no entries, no
history, an empty store.

**Tag upfront.** Executions tagged at record time can be purged in bulk by tag later.
`--tag <tag>` on `gmlcache run` takes effect immediately; you cannot retroactively tag
an entry (only `inspect` shows existing tags).

**Quota as a ceiling.** Set `max_size` to stop the store from growing unbounded in an
automated pipeline. Combine with regular `session report` runs so evicted entries are
still counted in usage summaries before the bytes disappear.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
