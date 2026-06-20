<div align="center">

# Configuration Reference

<sub>Reference</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> Reference pages are optimized for lookup. Start with the conceptual documents when you need background.

Configuration is resolved with clear precedence. Every setting has a built-in
default, so a config file is optional; `gmlcache init` writes a starter file on
explicit request.

## Settings

| Key | Meaning | Default | Environment override |
|---|---|---|---|
| `mode` | Resolution mode: `cache`, `offline`, or `refresh`. | `cache` | `GMLCACHE_MODE` |
| `store` | Where cassettes live on disk. | per-user data dir (see below) | *(none — by design)* |
| `timeout` | Seconds before a real call is killed; empty means no timeout. | none | `GMLCACHE_TIMEOUT` |
| `trust_scan` | Whether `--allow-path` (scan) calls may be cached. `false` keeps them passthrough (always fresh, never stored); `true` asserts the scanned folders are stable and lets them cache. | `false` | `GMLCACHE_TRUST_SCAN` |
| `max_size` | Enables insertion-time size eviction; the store evicts least-recently-used cassettes to make room. | off | `GMLCACHE_MAX_SIZE` |

For `max_size` behavior see [Cache eviction](../concepts/cache-eviction.md).

## Precedence

For every setting except `store`, the resolution order is: **CLI flag →
environment variable → config file → built-in default**.

`store` is the deliberate exception — it resolves from the config file or the
built-in default only, with no flag and no environment override, because the store
is the cache's own internal structure rather than a per-call knob. To relocate it,
set `store` in the config file.

## Config file location

Override the file path entirely with `GMLCACHE_CONFIG=/path/to/config.ini`.
Otherwise the default is:

- Windows — `%APPDATA%\generic-ml-cache\config.ini`
- otherwise — `$XDG_CONFIG_HOME/generic-ml-cache/config.ini` (or
  `~/.config/generic-ml-cache/config.ini`)

The default `store` resolves to the per-user data directory (`$XDG_DATA_HOME` /
`%LOCALAPPDATA%`), under `generic-ml-cache`.

Color output follows the standard `NO_COLOR` convention and is suppressed when
output is not a terminal.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
