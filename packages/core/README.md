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

The reusable **hexagonal kernel** behind
[`gmlcache`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/cli):
record a real ML client (or API) call once, replay it by its content key. It contains
the domain model, the use cases, and the port contracts — the pure hexagonal kernel.
Concrete infrastructure (SQLite, filesystem blob store, ML client runners, API adapters,
metrics, clock, fingerprinting) lives in
[`generic-ml-cache-adapters`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/adapters).

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

`generic-ml-cache-core` provides the ports and use cases. Pair it with
[`generic-ml-cache-adapters`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/adapters)
for the shipped infrastructure, then wire them in your composition root:

```python
from generic_ml_cache_core import ApplicationApi
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)

# wired: ApplicationApi — constructed by your composition root (see adapters package)
command = RunMlExecutionCommand(
    execution_kind=ExecutionKind.LOCAL_MANAGED,
    client="claude", model="claude-sonnet-4-5", effort="", context="", prompt="…",
)
execution = wired.run_ml.execute(command)   # records on a miss, replays on a hit
```

Need a different store? Implement the ports from `generic_ml_cache_core.application.port`
and pass your own adapters. The core never imports any concrete implementation.

## What's inside

- **Domain model** — executions, polymorphic call identities, artifacts, usage.
- **Use cases** — managed-local / passthrough / API runs, and probe (check).
- **Ports** (`application/port/...`) — client runner, blob store, execution repository,
  metrics, clock, fingerprint, API client. The `gmlcache.adapters` entry-point group is
  discovered and resolved outside core (in the adapters package today).
- **`ApplicationApi`** — typed container of wired use-case references (constructed by
  the composition root in the adapters or CLI package).

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
