<div align="center">

<br>

# gmlcache

#### Detached ML Execution Cache

**Run**, **record**, and **replay** detached ML workloads — exact, content-addressed, and inspectable. Record a real client (or API) call once; replay it forever by its content key — offline and byte-for-byte.

<br>

[![Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-2563eb?style=for-the-badge)](LICENSE)
[![Alpha](https://img.shields.io/badge/Status-Alpha-d97706?style=for-the-badge)](docs/ROADMAP.md)
[![Adapters](https://img.shields.io/badge/Adapters-claude%20%C2%B7%20codex%20%C2%B7%20cursor--agent-7c3aed?style=for-the-badge)](docs/concepts/adapters.md)

<br>

[Install](#install)&nbsp;&nbsp;•&nbsp;&nbsp;[Usage](#usage)&nbsp;&nbsp;•&nbsp;&nbsp;[Two packages](#built-as-two-packages)&nbsp;&nbsp;•&nbsp;&nbsp;[Docs](docs/README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](docs/ROADMAP.md)

</div>

<br>

---

## Install

```bash
pip install generic-ml-cache-cli      # installs the `gmlcache` command (and the engine, generic-ml-cache-core)
```

## Usage

```bash
gmlcache run    --client claude --model sonnet --prompt "…"   # record on a miss, replay on a hit
gmlcache check  --client claude --model sonnet --prompt "…"   # is this exact call already cached?
gmlcache list                                                 # stored executions, grouped by client/model
gmlcache stats                                                # totals, hit counts, token usage and cost
gmlcache inspect <key>                                        # pretty-print one stored execution
gmlcache doctor | models | status | init                     # environment & configuration helpers
```

<div align="center">

<img src="docs/images/gmlcache-demo.gif" alt="gmlcache: check (miss) → run (records the real call) → check (hit) → run (instant cache replay)" width="900">

<sub>Same command twice: the first call runs the real client and records it; the second is served from cache, instantly and byte-identical.<br>▶ <a href="docs/images/gmlcache-demo.mp4">Watch in higher quality (MP4)</a></sub>

</div>

<br>

---

## Overview

gmlcache executes detached ML workloads through adapters, records the observable result of those executions, and replays them when the same execution request is seen again.

Its core cache is **exact and content-addressed**. The surrounding model gives callers inspection, usage reporting, cost visibility, and a path toward scoped, sessional, and asynchronous execution.

> [!NOTE]
> **gmlcache is not an interactive ML client.**
>
> It does not capture or replay conversations opened inside a client UI. It is for calls launched as detached work: a prompt, a model, declared inputs, grants, and a result.

<br>

## Built as two packages

`gmlcache` — the terminal client — is the face most people use. Behind it sits a **reusable engine** you can embed in your own application instead of driving it from a terminal.

| Package | What it is | Install |
|---|---|---|
| [`generic-ml-cache-cli`](packages/cli) | the `gmlcache` terminal client | `pip install generic-ml-cache-cli` |
| [`generic-ml-cache-core`](packages/core) | the engine — domain, use cases, ports, and the default adapters; **stateless and dependency-free** | `pip install generic-ml-cache-core` |

The CLI is one inbound driver over the engine; a daemon could be another. The engine ships everything but the user interface and the data source — to embed it, depend on the core and inject your own data source:

```python
from generic_ml_cache_core import build_use_cases

wired = build_use_cases(store_root="/path/you/choose")   # you provide the data source
result = wired.run_managed.execute(command)              # the engine does the rest
```

<br>

## Two sources of value

<table>
<tr>
<td width="50%" valign="top">

### ♻️ Avoided executions

When an execution request is **identical** to one already recorded, gmlcache replays the stored execution instead of calling the underlying client again.

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
| **Recording** | Records stdout, stderr, exit code, generated files, and usage metadata as an inspectable execution |
| **Replay** | Replays a matching execution without calling the underlying client again |
| **Inputs** | Fingerprints declared input files (path-sensitive) |
| **Trust** | Allows declared scan paths with explicit trust rules |
| **Grants** | Grants declared capabilities such as network, shell, read, and write where adapters support them |
| **Reporting** | Reports cache statistics, hits, records, usage, and saved client-reported cost |
| **Inspection** | Inspects and lists stored executions |

> [!NOTE]
> Size-based eviction, an alias (stdout-only) mode, scopes/sessions, and asynchronous
> execution are **planned, not yet implemented** — see the [roadmap](docs/ROADMAP.md).

<br>

## What is an execution request?

An **execution request** is the complete description of the work being launched. It includes the adapter, model, effort, prompt, context, declared input files, allowed paths, grants, passthrough client arguments, and execution mode.

> [!IMPORTANT]
> The prompt alone is not the call.
>
> Changing the model, effort, declared inputs, or capabilities can change what the underlying client can do and therefore changes cache identity.

<br>

## Why executions include files

gmlcache is **not** a stdout-only cache. Detached ML executions often create or modify files. Those files can be the real output of the execution: generated source code, configuration, documentation, migration files, or other artifacts.

For that reason, a stored execution records:

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
> The cache is "dumb" in one specific sense: it does not read, transform, or judge the meaning of the content.
>
> The richness of the tool lives in transport, recording, replay, and reporting.

gmlcache deliberately does not:

- interpret prompt meaning,
- decide whether two different prompts are "close enough",
- perform semantic caching,
- infer undeclared filesystem dependencies,
- act as a security sandbox,
- provide authentication or user-account management,
- record interactive client sessions,
- claim client-reported costs are authoritative billing.

<br>

## Documentation

The full documentation lives under [`docs/`](docs/README.md) — design, specification, usage, architecture, and concept guides — aligned to the hexagonal, two-package architecture. [`docs/domain-model.md`](docs/domain-model.md) is the normative reference for the domain model.

<br>

---

<div align="center">

Open source under the **Apache License 2.0**.

<sub>Governance: <a href="CONTRIBUTING.md">Contributing</a> · <a href="GOVERNANCE.md">Governance</a> · <a href="CODE_OF_CONDUCT.md">Code of Conduct</a> · <a href="SECURITY.md">Security</a> · <a href="AGENTS.md">Coding standard</a></sub>

</div>
