<div align="center">

# Usage

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

## At a glance

- [Core commands](#core-commands)
- [Modes](#modes)
- [Inputs](#inputs)
- [Files](#files)
- [Usage output](#usage-output)

---

This document describes the current CLI at a conceptual level. Use `gmlcache --help`
for the exact command syntax of the installed version.

## Core commands

| Command | Purpose |
|---|---|
| `run` | Execute or replay an execution request |
| `check` | Forecast hit/miss/non-cacheable without launching the adapter |
| `list` | List stored executions |
| `inspect` | Inspect a stored execution |
| `stats` | Report store and replay statistics |
| `doctor` | Inspect configured client availability |
| `models` | Ask an adapter for model listings when supported |
| `status` | Show resolved configuration |
| `init` | Materialize the config file |

## Modes

- `offline`: serve only from cache.
- `cache`: serve hits, record misses when cacheable.
- `refresh`: call the adapter and record a fresh execution.

## Inputs

Declared input files are fingerprinted by content and included in the key.
Allowed paths can be granted for scanning, but are non-cacheable by default unless
scan trust is enabled.

## Files

In full execution mode, generated files are captured from the isolated execution
folder. On replay, the cache can reproduce those files as part of the recorded
result.

## Usage output

`run --json`, `inspect`, and `stats` expose usage information where recorded. Cost
values are client estimates when available.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
