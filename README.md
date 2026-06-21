<div align="center">

<br>

# gmlcache

#### Detached ML Execution Platform

A cache that **runs**, **records**, and **replays** detached ML workloads — exact, content-addressed, and inspectable.

<br>

[![Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-2563eb?style=for-the-badge)](LICENSE)
[![Alpha](https://img.shields.io/badge/Status-Alpha-d97706?style=for-the-badge)](docs/ROADMAP.md)
[![Adapters](https://img.shields.io/badge/Adapters-claude%20%C2%B7%20codex%20%C2%B7%20cursor--agent-7c3aed?style=for-the-badge)](docs/concepts/adapters.md)

<br>

[Design](docs/design.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Specification](docs/SPEC.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Usage](docs/usage.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Storage](docs/storage.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](docs/ROADMAP.md)

</div>

<br>

> [!IMPORTANT]
> The codebase has moved to a hexagonal (ports-and-adapters) architecture and the
> on-disk **"cassette"** record format is retired (records are now *executions* in a
> SQLite store + blob store). Some `docs/` pages still describe the old format and are
> being rewritten for the v0.x architecture — see the [docs index](docs/README.md).

---

## Overview

gmlcache executes detached ML workloads through adapters, records the observable result of those executions, and replays them when the same execution request is seen again.

Its core cache is **exact and content-addressed**. The surrounding model gives callers inspection, usage reporting, cost visibility, and a path toward scoped, sessional, and asynchronous execution.

> [!NOTE]
> **gmlcache is not an interactive ML client.**
>
> It does not capture or replay conversations opened inside a client UI. It is for calls launched as detached work: a prompt, a model, declared inputs, grants, and a result.

<br>

## Two sources of value

<table>
<tr>
<td width="50%" valign="top">

### ♻️ Avoided executions

When an execution request is **identical** to one already recorded, gmlcache replays the cassette instead of calling the underlying client again.

</td>
<td width="50%" valign="top">

### 🔭 Observability

Even on a **cache miss**, executions can still be inspected, listed, grouped, and measured. Usage and cost information are recorded when clients provide it.

Future scope and session features build on that same metadata to report cost and cache performance across a workflow.

</td>
</tr>
</table>

<br>

## What it does today

| Capability | Description |
|---|---|
| **Adapters** | Runs supported detached CLI adapters: `claude`, `codex`, `cursor-agent` |
| **Cache key** | Builds a cache key from the full execution request, not from prompt text alone |
| **Recording** | Records stdout, stderr, exit code, generated files, and usage metadata into an inspectable cassette |
| **Replay** | Replays a matching cassette without calling the underlying client again |
| **Inputs** | Fingerprints declared input files |
| **Trust** | Allows declared scan paths with explicit trust rules |
| **Grants** | Grants declared capabilities such as network, shell, read, and write where adapters support them |
| **Reporting** | Reports cache statistics, hits, records, usage, and saved client-reported cost |
| **Inspection** | Inspects and lists recorded cassettes |
| **Eviction** | Enforces optional size-based LRU eviction on insertion |

<br>

## What is an execution request?

An **execution request** is the complete description of the work being launched. It includes the adapter, model, effort, prompt, context, declared input files, allowed paths, grants, passthrough client arguments, and execution mode.

> [!IMPORTANT]
> The prompt alone is not the call.
>
> Changing the model, effort, declared inputs, or capabilities can change what the underlying client can do and therefore changes cache identity.

<br>

## Why cassettes include files

gmlcache is **not** a stdout-only cache. Detached ML executions often create or modify files. Those files can be the real output of the execution: generated source code, configuration, documentation, migration files, or other artifacts.

For that reason, a cassette records:

- stdout,
- stderr,
- exit code,
- generated files,
- usage metadata when available,
- the execution request identity that produced the result.

> [!TIP]
> If a caller only needs stdout and never wants generated artifacts, a simpler alias-style wrapper may eventually be sufficient.
>
> The full execution model exists for the richer case where files matter.

<br>

## Deliberate non-goals

> [!CAUTION]
> The cache is “dumb” in one specific sense: it does not read, transform, or judge the meaning of the content.
>
> The richness of the tool lives in transport, recording, replay, and reporting.

gmlcache deliberately does not:

- interpret prompt meaning,
- decide whether two different prompts are “close enough”,
- perform semantic caching,
- infer undeclared filesystem dependencies,
- act as a security sandbox,
- provide authentication or user-account management,
- record interactive client sessions,
- claim client-reported costs are authoritative billing.

<br>

## Documentation

<table>
<tr>
<td width="50%" valign="top">

### Start here

| Document | Purpose |
|---|---|
| [Design](docs/design.md) | Project principles and why the system works this way |
| [Specification](docs/SPEC.md) | Current conceptual model |
| [Usage](docs/usage.md) | Current CLI behavior |
| [Storage](docs/storage.md) | Cassette store, registry, and eviction |
| [Roadmap](docs/ROADMAP.md) | Versioned path from current alpha to 1.x |

</td>
<td width="50%" valign="top">

### Concepts

- [Execution requests](docs/concepts/execution-requests.md)
- [Cassettes](docs/concepts/cassettes.md)
- [Adapters](docs/concepts/adapters.md)
- [Grants](docs/concepts/grants.md)
- [Observability](docs/concepts/observability.md)
- [Cost and usage](docs/concepts/cost-and-usage.md)
- [Cache eviction](docs/concepts/cache-eviction.md)
- [Alias mode](docs/concepts/alias-mode.md)
- [Scopes and sessions](docs/concepts/scopes-and-sessions.md)
- [Asynchronous executions](docs/concepts/asynchronous-executions.md)

</td>
</tr>
</table>

<br>

---

<div align="center">

Open source under the **Apache License 2.0**.

<sub>`CONTRIBUTING.md` · `GOVERNANCE.md` · `SECURITY.md` · `LICENSE` are intentionally maintained outside this documentation replacement.</sub>

</div>
