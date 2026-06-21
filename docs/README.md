<div align="center">

# Documentation

#### gmlcache documentation map

A guided entry point for the design, specification, usage, architecture, reference, and future-direction documents.

<br>

[Repository README](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Design](design.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Specification](SPEC.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Usage](usage.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](ROADMAP.md)

</div>

---

> [!IMPORTANT]
> **Docs are being rewritten for the v0.x hexagonal architecture.** The codebase
> was refactored to ports-and-adapters and the on-disk **"cassette"** record format
> was retired (records are now *executions* in a SQLite store + content-addressed
> blob store). Pages that still describe the cassette format or a single-package
> layout — notably `concepts/cassettes.md` and `reference/cassette-schema.md` — are
> **out of date** and will be rewritten after the planned core/CLI package split.
> Treat the source (`src/generic_ml_cache/`) and `docs/domain-model.md` as the
> ground truth until then.

## Overview

This documentation describes gmlcache as a Detached ML Execution Platform: an exact record/replay cache with adapter-based execution, inspectable execution records, usage reporting, and planned scope/session/async features.

<br>

## Start here

| Document | Purpose |
|---|---|
| [Design](design.md) | Project identity, principles, and design constraints |
| [Specification](SPEC.md) | Current conceptual specification and terminology |
| [Usage](usage.md) | Current CLI behavior at a conceptual level |
| [Storage](storage.md) | Cassette layout, registry, eviction, and future storage rules |
| [Client mapping](client-mapping.md) | Common request fields and adapter differences |
| [Roadmap](ROADMAP.md) | Current alpha capability and path to 1.x |

<br>

## Concepts

<table>
<tr>
<td width="50%" valign="top">

- [Execution requests](concepts/execution-requests.md)
- [Cassettes](concepts/cassettes.md)
- [Adapters](concepts/adapters.md)
- [Grants](concepts/grants.md)
- [Observability](concepts/observability.md)

</td>
<td width="50%" valign="top">

- [Cost and usage](concepts/cost-and-usage.md)
- [Cache eviction](concepts/cache-eviction.md)
- [Alias mode](concepts/alias-mode.md)
- [Scopes and sessions](concepts/scopes-and-sessions.md)
- [Asynchronous executions](concepts/asynchronous-executions.md)

</td>
</tr>
</table>

<br>

## Architecture

| Document | Focus |
|---|---|
| [Execution engine](architecture/execution-engine.md) | How executions are launched, recorded, and replayed |
| [Storage model](architecture/storage-model.md) | How cassettes and metadata are organized |
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
| [Cassette schema](reference/cassette-schema.md) | Cassette structure and normalized fields |

<br>

## Future

| Future area | Document |
|---|---|
| Provider/API execution | [API adapters](future/api-adapters.md) |
| Long-running service mode | [Daemon transport](future/daemon-transport.md) |
| Storage lifecycle | [Retention and invalidation](future/retention-and-invalidation.md) |

---

<div align="center">

<sub><a href="../README.md">Repository README</a></sub>

</div>
