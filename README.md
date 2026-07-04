<div align="center">

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/gmlcache-lockup-dark.svg">
  <img src="docs/images/gmlcache-lockup.svg" alt="gmlcache" width="320">
</picture>

#### Detached ML Execution Cache

**Run**, **record**, and **replay** detached ML workloads — exact, content-addressed, and inspectable. Record a real client (or API) call once; replay it forever by its content key — offline and byte-for-byte.

<br>

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-185FA5?style=for-the-badge&labelColor=403E3A)](LICENSE)
[![Status: Beta](https://img.shields.io/badge/status-beta-BA7517?style=for-the-badge&labelColor=403E3A)](docs/ROADMAP.md)

[![CLI adapter: claude](https://img.shields.io/badge/cli-claude-534AB7?style=for-the-badge&labelColor=3C3489)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/client/claude.py)
[![CLI adapter: codex](https://img.shields.io/badge/cli-codex-534AB7?style=for-the-badge&labelColor=3C3489)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/client/codex.py)
[![CLI adapter: cursor-agent](https://img.shields.io/badge/cli-cursor--agent-534AB7?style=for-the-badge&labelColor=3C3489)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/client/cursor.py)

[![API adapter: anthropic](https://img.shields.io/badge/api-anthropic-0F6E56?style=for-the-badge&labelColor=085041)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/api/anthropic_direct_adapter.py)
[![API adapter: openai](https://img.shields.io/badge/api-openai-0F6E56?style=for-the-badge&labelColor=085041)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/api/openai_direct_adapter.py)
[![API adapter: gemini](https://img.shields.io/badge/api-gemini-0F6E56?style=for-the-badge&labelColor=085041)](packages/adapters/src/generic_ml_cache_adapters/adapter/outbound/api/gemini_direct_adapter.py)

<br>

[Install](#install)&nbsp;&nbsp;•&nbsp;&nbsp;[Five packages](#five-packages)&nbsp;&nbsp;•&nbsp;&nbsp;[Docs](docs/README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](docs/ROADMAP.md)

</div>

<br>

---

## Install

```bash
pip install generic-ml-cache-cli      # gmlcache command + the engine (generic-ml-cache-core)
pip install generic-ml-cache-daemon   # optional: local HTTP API (gmlcache daemon)
```

## Overview

gmlcache executes detached ML workloads through adapters, records the observable result of those executions, and replays them when the same execution request is seen again.

Its core cache is **exact and content-addressed**. Around it: inspection, per-session usage reporting, at-rest encryption, and detached (asynchronous) execution with a live progress stream.

> [!NOTE]
> **gmlcache is not an interactive ML client.**
>
> It does not capture or replay conversations opened inside a client UI. It is for calls launched as detached work: a prompt, a model, declared inputs, grants, and a result.

<br>

## What gmlcache is — and what it isn't

gmlcache is a **single-user** tool for discovering, testing, and integrating AI: it records a real call once and replays it forever by checksum, across whichever subscriptions and APIs **you already hold**. It runs **locally, on your machine, as you**.

It is **not** a **multi-user** gateway or router, and **not** a way to make one subscription serve several people. It *does* ship a local, single-principal caching proxy (the daemon's `/gateway/claude` route) for your own calls on your own machine — but that binds localhost and is single-user by design, not a shared gateway. If you want a multi-user gateway, the market already has them (LiteLLM, Portkey, Helicone, …) — gmlcache deliberately isn't one.

> [!IMPORTANT]
> **Being upfront.** Because gmlcache drives the vendors' *own* CLIs, you *could* wire it to front one subscription for many people — the tool doesn't technically stop you, the same way `git` doesn't stop a bad commit. But that is a violation of **your** provider's terms that **you** commit, identical to sharing your password, and it is explicitly **not** what gmlcache is for. We're not hiding behind "it's impossible" — it isn't impossible; it's simply not the intent, and respecting your provider's licence is your responsibility.

→ Full reasoning, the boundaries, and where it shines: **[Positioning](docs/design/positioning.md)**.

<br>

## Five packages

`gmlcache` — the terminal client — is the face most people use. Behind it sits a **reusable engine** you can embed in your own application, a **composition root** that wires it, and an optional **HTTP daemon** that exposes the same cache as a local REST API.

| Package | What it is | Install |
|---|---|---|
| [`generic-ml-cache-cli`](packages/cli) | the `gmlcache` terminal client | `pip install generic-ml-cache-cli` |
| [`generic-ml-cache-core`](packages/core) | the hexagonal kernel — domain model, use cases, and port contracts | `pip install generic-ml-cache-core` |
| [`generic-ml-cache-adapters`](packages/adapters) | concrete port implementations — SQLite, filesystem, ML clients, API adapters, encryption | `pip install generic-ml-cache-adapters` |
| [`generic-ml-cache-bootstrap`](packages/bootstrap) | the composition root — wires core + adapters, discovers ML-runner plugins, runs the boot version handshake | `pip install generic-ml-cache-bootstrap` |
| [`generic-ml-cache-daemon`](packages/daemon) | local HTTP API over the cache store; gateway proxy | `pip install generic-ml-cache-daemon` |

The CLI and the daemon are both inbound drivers over the same engine. The dependency arrows point inward: `adapters → core`, and `bootstrap → core + adapters` (the one place allowed to import both). The core knows nothing about concrete infrastructure — it depends only on the port contracts, and the data source is injected by the caller. To embed the engine, depend on `generic-ml-cache-core` for the ports and use cases, `generic-ml-cache-adapters` for the shipped infrastructure, and `generic-ml-cache-bootstrap` to wire them into a ready `ApplicationApi`:

```python
from generic_ml_cache_bootstrap.application import build_application_api
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)

# build_application_api returns an ApplicationApi — the bundle of inbound-port
# fields the drivers call. Inject your own PersistenceBackend / blob store to run
# on Postgres/S3; inject nothing for the batteries-included SQLite + filesystem stack.
wired = build_application_api(store_root, build_runners)
result = wired.run_ml.execute(RunMlExecutionCommand(...))
```

<br>

## Adapters

gmlcache ships built-in adapters for every port in the engine. Because the architecture is ports-and-adapters, additional backends slot in without touching the domain logic.

### Client adapters

| Adapter | Kind | Core | CLI | Daemon |
|---|---|:---:|:---:|:---:|
| `claude` | Managed CLI | ✅ | ✅ | — |
| `codex` | Managed CLI | ✅ | ✅ | — |
| `cursor-agent` | Managed CLI | ✅ | ✅ | — |
| `anthropic` | REST API | ✅ | ✅ | ✅ |
| `openai` | REST API | ✅ | ✅ | ✅ |
| `gemini` | REST API | ✅ | ✅ | ✅ |

**Managed CLI** adapters drive the vendor's installed binary as a subprocess; the cache wraps the process boundary. **REST API** adapters call the provider endpoint directly using stdlib HTTP — no third-party SDK required.

### Storage

The engine stores executions across two complementary backends, both zero-config by default and built on only the Python standard library.

| Backend | Role | Status |
|---|---|:---:|
| Filesystem | Blob store — stdout, stderr, generated files, at-rest encryption | ✅ |
| SQLite | Index & metadata — cache keys, usage, tags, session records | ✅ |

The storage layer is a set of outbound ports. A PostgreSQL persistence adapter or an S3 blob adapter would implement the same port interfaces and be wired in at the composition root — no engine changes required.

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

Sessions build on that same metadata: `session report` rolls up a workflow's runs by provider/model — tokens spent and saved by cache hits, per day.

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
| **Persistence depth** | `meter` (usage only) · `cache` (+ output) · `dataset` (+ input), per run |
| **Tags & export** | Tags executions, queries by tag, and exports the `(input, output)` dataset as JSONL |
| **Encryption** | Optional at-rest encryption of the whole store — token-keyed, all-or-nothing |
| **Sessions** | Groups a workflow's runs; `session report` rolls up usage by provider/model + cache savings |
| **Detached** | `run --detach` returns an id; query / watch / fetch / materialize the result later |
| **Live streaming** | `run --stream` (and `execution watch`) emit the client's live progress as NDJSON |
| **Alias** | `alias <client> -- <native args>` — a thin wrapper that caches a raw native call (stdout/stderr/exit) |

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
> If a caller only needs stdout and never wants generated artifacts, the simpler
> [alias mode](docs/reference/cli.md#alias-mode) (`gmlcache alias <client> -- …`) is enough.
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

The full documentation lives under [`docs/`](docs/README.md) — design, specification, usage, architecture, and concept guides. [`docs/domain-model.md`](docs/domain-model.md) is the normative reference for the domain model.

<br>

---

<div align="center">

Open source under the **Apache License 2.0**.

<sub>Governance: <a href="CONTRIBUTING.md">Contributing</a> · <a href="GOVERNANCE.md">Governance</a> · <a href="CODE_OF_CONDUCT.md">Code of Conduct</a> · <a href="SECURITY.md">Security</a> · <a href="AGENTS.md">Coding standard</a></sub>

</div>
