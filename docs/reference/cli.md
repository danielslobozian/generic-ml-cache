<div align="center">

# CLI Reference

<sub>Reference</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> Reference pages are optimized for lookup. Start with the conceptual documents when you need background.

## At a glance

- [Current commands](#current-commands)
- [Future scope/session commands](#future-scopesession-commands)
- [Future async commands](#future-async-commands)
- [Future alias mode](#future-alias-mode)

---

This reference contains the intended command surface. Exact syntax may differ by
release; use `gmlcache --help` for the installed version.

## Current commands

```text
gmlcache run ...
gmlcache check ...
gmlcache list
gmlcache inspect <key-or-prefix>
gmlcache stats
gmlcache doctor
gmlcache models <client>
gmlcache status
gmlcache init
```

## Future scope/session commands

```text
gmlcache scope create
gmlcache scope invalidate --scope-token <token>
gmlcache scope report --scope-token <token>

gmlcache session start --scope-token <token>
gmlcache session report <session-id> --scope-token <token>
gmlcache session watch <session-id> --scope-token <token>
```

## Future async commands

```text
gmlcache run --detach ...
gmlcache execution status <execution-id>
gmlcache execution watch <execution-id>
gmlcache execution result <execution-id>
gmlcache execution materialize <execution-id> --output-dir <path>
```

## Future alias mode

```text
gmlcache alias <adapter> <native adapter arguments...>
```

Everything after `<adapter>` is native adapter input and is included in cache
identity as an opaque tail.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
