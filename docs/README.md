<div align="center">

# Documentation

#### gmlcache documentation map

A guided entry point for the design, specification, usage, architecture, reference, and future-direction documents.

<br>

[Repository README](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Design](design.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Specification](SPEC.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Usage](usage.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](ROADMAP.md)

</div>

---

> [!NOTE]
> The codebase is organized as three packages: `packages/core` (the library),
> `packages/cli` (the `gmlcache` client), and `packages/daemon` (the local HTTP
> daemon). Records are *executions* stored in a SQLite store with a content-addressed
> blob store. The architecture is hexagonal (ports-and-adapters); treat
> [`domain-model.md`](domain-model.md) as the normative domain reference.

## Overview

This documentation describes gmlcache as a Detached ML Execution Platform: an exact record/replay cache with adapter-based execution, inspectable execution records, usage reporting, sessions with per-model reporting, at-rest encryption, and detached (asynchronous) execution with live progress streaming.

<br>

## Start here

| Document | Purpose |
|---|---|
| [Design](design.md) | Project identity, principles, and design constraints |
| [Positioning](design/positioning.md) | What gmlcache is and is not — the single-user intent |
| [Specification](SPEC.md) | Current conceptual specification and terminology |
| [Usage](usage.md) | Current CLI behavior at a conceptual level |
| [Storage](storage.md) | The execution store (SQLite) and content-addressed blob store |
| [Client mapping](client-mapping.md) | Common request fields and adapter differences |
| [Roadmap](ROADMAP.md) | Current alpha capability and path to 1.x |
| [Compatibility policy](compatibility.md) | What is stable at 1.0.0, Python support, schema and adapter promises |

<br>

## Concepts

<table>
<tr>
<td width="50%" valign="top">

- [Execution requests](concepts/execution-requests.md)
- [Executions](concepts/executions.md)
- [Adapters](concepts/adapters.md)
- [Grants](concepts/grants.md)
- [Observability](concepts/observability.md)

</td>
<td width="50%" valign="top">

- [Cost and usage](concepts/cost-and-usage.md)
- [Alias mode](concepts/alias-mode.md)
- [Sessions](concepts/sessions.md)
- [Asynchronous executions](concepts/asynchronous-executions.md)
- [Retention and quota](concepts/retention.md)

</td>
</tr>
</table>

<br>

## Architecture

| Document | Focus |
|---|---|
| [Execution engine](architecture/execution-engine.md) | How executions are launched, recorded, and replayed |
| [Storage model](architecture/storage-model.md) | How execution records and output blobs are organized |
| [Adapter contract](architecture/adapter-contract.md) | What adapters must provide to the engine |

<br>

## Use cases

| Use case | Document |
|---|---|
| Repeated automation | [CI/CD and repeated pipelines](use-cases/ci-cd.md) |
| Workflow orchestration | [Workflow engines](use-cases/workflow-engines.md) |
| Measurement and reporting | [Cost and usage analysis](use-cases/cost-and-usage-analysis.md) |
| Evaluation and comparison | [Provider and model experiments](use-cases/provider-and-model-experiments.md) |

<br>

## Reference

| Reference | Contents |
|---|---|
| [CLI reference](reference/cli.md) | Current and future command groups |
| [Configuration](reference/configuration.md) | Supported configuration keys |
| [Grants reference](reference/grants.md) | Current and planned grant vocabulary |

<br>

## Future

| Future area | Document |
|---|---|
| Provider/API execution | [API adapters](future/api-adapters.md) |
| Long-running service mode | [Daemon transport](future/daemon-transport.md) |

---

<div align="center">

<sub><a href="../README.md">Repository README</a></sub>

</div>
