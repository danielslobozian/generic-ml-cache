<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-lockup-dark.png">
  <img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-lockup.png" alt="gmlcache" width="300">
</picture>
</p>

#### Detached ML Execution Cache — the terminal client

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-2563eb?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-d97706?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/ROADMAP.md)

`gmlcache` runs, records, and replays detached ML workloads — record a real client (or
API) call once, replay it forever by its content key, offline and byte-for-byte.

> **Single-user, local — not a gateway.** gmlcache runs on your machine, as you, across the
> subscriptions and APIs you already hold. It is **not** a multi-user router and **not** a way
> to share one subscription — see
> [Positioning](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/design/positioning.md).

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-demo.gif" alt="gmlcache: a miss records the real client call; the same command again is served instantly from cache, byte-identical" width="760">
</p>

## Install

```bash
pip install generic-ml-cache-cli
```

This installs the `gmlcache` command and pulls in the engine,
[`generic-ml-cache-core`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/core).

## Use

```bash
gmlcache run    --client claude --model sonnet --prompt "…"   # record on a miss, replay on a hit
gmlcache check  --client claude --model sonnet --prompt "…"   # is this exact call already cached?
gmlcache list                                                 # stored executions, grouped by client/model
gmlcache stats                                                # totals, hit counts, token usage & cost
gmlcache inspect <key>                                        # pretty-print one stored execution
gmlcache doctor | models | status | init                     # environment & configuration helpers
```

## What it does

- **Records** a real agentic CLI client (`claude`, `codex`, `cursor-agent`) or an API
  call — stdout, stderr, exit code, generated files, and token usage.
- **Replays** an identical request instantly and offline, **byte-for-byte** — gmlcache
  adds nothing to the client's output, so it is a transparent drop-in.
- **Reports** — list, group, inspect, and measure stored executions and their savings.

## Built on a reusable engine

`gmlcache` is the terminal client — one inbound driver over the engine. The whole cache
logic and every adapter live in
[`generic-ml-cache-core`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/core),
a **stateless** library. To embed the cache in your own application
instead of driving it from a terminal, depend on the core and inject your own data
source — you never reimplement the adapters.

## Links

- **Repository & docs:** <https://github.com/danielslobozian/generic-ml-cache>
- **Changelog** (both packages, versioned in lockstep): [`CHANGELOG.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/CHANGELOG.md)
- **Security policy:** [`SECURITY.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/SECURITY.md)

## License

Apache-2.0 — see [`LICENSE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
and [`NOTICE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/NOTICE).
