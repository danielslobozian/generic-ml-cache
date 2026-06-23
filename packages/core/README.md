<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-mark-dark.png">
  <img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-mark.png" alt="gmlcache" width="72">
</picture>
</p>

# generic-ml-cache-core

#### The hexagonal engine behind gmlcache — embeddable and stateless

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-2563eb?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-d97706?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/ROADMAP.md)

The reusable **engine** behind
[`gmlcache`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/cli):
record a real ML client (or API) call once, replay it by its content key. It contains
the domain model, the use cases, the port contracts, **and the default outbound
adapters** (SQLite execution repository, filesystem blob store, the
claude/codex/cursor client runner, the API client, metrics, clock, fingerprinting) —
plus the `build_use_cases` composition factory.

Pure Python and **stateless**: it bakes in *structure*
(table names, blob naming, schema) but no *location* — you inject the data source.

> **Part of a single-user, local tool — not a gateway.** gmlcache records and replays across
> the subscriptions and APIs you already hold; it is **not** a multi-user router. See
> [Positioning](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/design/positioning.md).

## Install

```bash
pip install generic-ml-cache-core
```

## Embed it

Hand the library a data source and it wires the engine for you:

```python
from generic_ml_cache_core import build_use_cases
from generic_ml_cache_core.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)

wired = build_use_cases(store_root="/path/you/choose")   # you provide the data source
command = RunManagedLocalExecutionCommand(
    client="claude", model="sonnet", effort="", context="", prompt="…",
)
execution = wired.run_managed.execute(command)           # records on a miss, replays on a hit
```

You reuse the shipped adapters by injecting a data source — you never reimplement them
(the **Spring Batch** model: the framework ships the writers, you provide the
connection). Need a different store? Construct the use cases yourself against the
ports and pass your own adapter.

## What's inside

- **Domain model** — executions, polymorphic call identities, artifacts, usage.
- **Use cases** — managed-local / passthrough / API runs, and probe (check).
- **Ports** (`application/port/...`) — client runner, blob store, execution repository,
  metrics, clock, fingerprint, API client.
- **Default adapters** (`adapter/out/...`) + the `build_use_cases` composition factory.
- **`generic_ml_cache_core.testing.InMemoryExecutionRepository`** — an in-memory
  reference adapter to test your code against the ports.

Inbound drivers —
[`gmlcache`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/cli)
today, a daemon later — map their surface (a terminal, a REST API) onto these public
APIs; the core itself has no UI and reads no config file.

## Links

- **Repository & docs:** <https://github.com/danielslobozian/generic-ml-cache>
- **Changelog** (both packages, versioned in lockstep): [`CHANGELOG.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/CHANGELOG.md)
- **Security policy:** [`SECURITY.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/SECURITY.md)

## License

Apache-2.0 — see [`LICENSE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
and [`NOTICE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/NOTICE).
