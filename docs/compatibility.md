<div align="center">

# Compatibility Policy

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

## At a glance

- [Alpha (0.x): no stability guarantee](#alpha-0x-no-stability-guarantee)
- [What is stable at 1.0.0](#what-is-stable-at-100)
- [Python version support](#python-version-support)
- [Execution-record schema promise](#execution-record-schema-promise)
- [Adapter contract promise](#adapter-contract-promise)
- [Migration promise: 0.x → 1.0.0](#migration-promise-0x--100)

---

## Alpha (0.x): no stability guarantee

While the version is `0.x.y`, gmlcache is **alpha**. Any of the following may change
between minor releases without notice or a deprecation period:

- CLI command names, flags, and output format
- Configuration keys and their semantics
- The execution-record schema (table names, column names, SQL DDL)
- The public Python API (`generic_ml_cache_core.__all__`)
- The adapter contract (port interfaces, registry protocol, entry-point group)
- The blob store layout on disk
- The daemon HTTP API paths and response shapes

Patch releases (`0.x.y → 0.x.z`) fix bugs without introducing breaking changes to
anything that was working in `0.x.0`. If a patch release must break something to fix a
correctness issue, that is noted explicitly in the changelog.

---

## What is stable at 1.0.0

`1.0.0` is the point at which the alpha tag is removed. From `1.0.0` onwards the
following surfaces are locked under the promise described in the sections below:

| Surface | Stable element |
|---|---|
| **CLI** | All command names, flag names, positional arguments, and exit codes documented in [`docs/reference/cli.md`](reference/cli.md). Output formats for `--json` flags. |
| **Python API** | Every name in `generic_ml_cache_core.__all__` — its signature, its semantics, and its exception contract. |
| **Adapter contract** | The `MlRunnerPort` / `ClientAdapter` / `ApiClientPort` interfaces, the `@register` / `get_adapter` registry API, the `gmlcache.adapters` entry-point group, and the `adapter_contract_version` compatibility check. |
| **Execution-record schema** | The logical record format (fields, types, relationships) as documented in [`docs/storage.md`](storage.md). The physical SQLite DDL is an implementation detail and may be migrated transparently. |
| **Configuration** | All keys documented in [`docs/reference/configuration.md`](reference/configuration.md), their types, and their precedence order (default → file → env → flag). |

Anything not in the table above is internal and may change between `1.x` minor
releases. Internal paths (`adapter/out/…`, `adapter/inbound/…`, `migrations/`) are
not covered by this promise even if they are importable.

---

## Python version support

gmlcache supports **CPython 3.9 and later**. The supported range follows the
[Python release calendar](https://devguide.python.org/versions/):

- A Python version is **added** when it reaches general availability.
- A Python version is **dropped** no sooner than its end-of-life date and only in a
  new minor release (never a patch), with the drop noted in the changelog.

The currently tested range is **3.9 – 3.13**. The CI matrix covers all versions in this
range on Linux; 3.12 and 3.13 are additionally tested on macOS and Windows.

PyPy and other alternative implementations are not officially supported. They may work,
but no CI coverage is provided and breakage reports are best-effort only.

---

## Execution-record schema promise

### During 1.x

A store created by any `1.x` release can be read and written by any later `1.x`
release. Schema changes within `1.x` are additive only (new tables, new nullable
columns, new indexes). No column or table is dropped or renamed within `1.x`.

The migration runner (`run_migrations`) applies any pending additions automatically on
first use — no manual intervention required.

### Across major versions (future)

A store created by `1.x` is not guaranteed to be readable by `2.x` without an explicit
migration step. The `2.x` release notes will describe the migration path.

### What the schema promise does not cover

- The physical SQLite file name (`executions.sqlite3`) and its location relative to the
  store root — these are implementation details.
- The blob store directory layout — content-addressed paths may be reorganized in a
  major version with a migration step.
- The `schema_version` table format — this is internal to the migration runner.

---

## Adapter contract promise

### Contract version

The adapter contract is versioned via `ADAPTER_CONTRACT_VERSION` (currently `"1"`).
A third-party adapter declares compatibility by setting:

```python
class MyAdapter(ClientAdapter):
    adapter_contract_version = "1"
```

An adapter that omits `adapter_contract_version` is treated as compatible. An adapter
that declares a different version emits a warning and is skipped at load time.

### During 1.x

An adapter written against contract version `"1"` will continue to load and function
correctly across all `1.x` releases. The following are guaranteed:

- `MlRunnerPort`, `ClientAdapter`, `ApiClientPort` — no method removed or renamed;
  new optional methods may be added with default no-op implementations.
- `@register` / `get_adapter` — signatures unchanged.
- `gmlcache.adapters` entry-point group — name unchanged; discovery protocol unchanged.
- `RunMlExecutionCommand` — no field removed; new optional fields may be added with
  defaults.

### Contract version bump

When the adapter contract changes in a breaking way, `ADAPTER_CONTRACT_VERSION` is
incremented. This will not happen within `1.x`. A bump, if it occurs, will be in a
major version (`2.0.0`) with a clear migration guide.

---

## Migration promise: 0.x → 1.0.0

A store created by any `0.x` release (from 0.17.0 onward, when the unified schema was
introduced) will be automatically migrated to the 1.0.0 schema by running the new
binary once:

```sh
gmlcache doctor   # or any other gmlcache command
```

The migration runner applies pending migrations atomically on startup. No data is lost.
No manual SQL is required.

Stores created before 0.17.0 used a different on-disk format and are not supported for
automatic migration. The upgrade path from pre-0.17.0 is: upgrade to any 0.17.x–0.23.x
release first, then upgrade to 1.0.0.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
