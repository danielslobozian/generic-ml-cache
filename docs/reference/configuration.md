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

## At a glance

- [Settings table](#settings-table)
- [Section: `[executables]`](#section-executables)
- [`version` key](#version-key)
- [Precedence order](#precedence-order)
- [Config file location](#config-file-location)
- [Validating and inspecting](#validating-and-inspecting)

---

## Settings table

All keys live in the `[defaults]` section of the INI file.

| Key | Type | Default | Env override | Description |
|---|---|---|---|---|
| `mode` | `cache` \| `offline` \| `refresh` | `cache` | `GMLCACHE_MODE` | Resolution mode. `cache` = replay on hit, call on miss. `offline` = replay or fail. `refresh` = always call, always record. |
| `persist` | `meter` \| `cache` \| `dataset` | `cache` | `GMLCACHE_PERSIST` | How much to keep. `meter` = usage/metadata only (no replay). `cache` = + output (replay on hit). `dataset` = + input (exportable corpus). |
| `store` | path | per-user data dir | *(none — by design)* | Where the store lives on disk. No flag, no env — see [Precedence order](#precedence-order). |
| `timeout` | number (seconds) | none | `GMLCACHE_TIMEOUT` | Seconds before a real call is killed. Empty/omitted means no timeout. |
| `trust_scan` | boolean | `false` | `GMLCACHE_TRUST_SCAN` | Whether `--allow-path` (folder scan) calls may be cached. `false` keeps them passthrough. `true` asserts the scanned folders are stable. |
| `max_size` | size string | off | `GMLCACHE_MAX_SIZE` | Storage quota. When set, LRU eviction keeps the store at or below this size after each new record. Accepted suffixes: `5GB`, `500MB`, `100KB`, or a plain byte count. |
| `max_age` | duration string | off | `GMLCACHE_MAX_AGE` | Maximum time since last access before an entry is considered stale. The daemon evicts stale entries on a background schedule. Accepted suffixes: `30d`, `12h`, `3600s`, `2w`. |
| `adapters` | `*` or comma-separated names | `*` (all) | *(none)* | Restricts which adapters are active. `adapters = *` or omitting the key means all installed adapters are available. Any session or run referencing a disabled adapter fails immediately. |
| `log_level` | `DEBUG` \| `INFO` \| `WARN` \| `ERROR` | off | `GMLCACHE_LOG_LEVEL` | Enables technical diagnostic logging at the given severity. When omitted, no diagnostic log is written. |
| `log_file` | path | `<store>/gmlcache.log` | `GMLCACHE_LOG_FILE` | Destination file for diagnostic logs. Only consulted when `log_level` is set. |
| `version` | integer string | *(omit)* | *(none)* | Optional config schema version. See [`version` key](#version-key). |

### Boolean values

`trust_scan` accepts: `true`, `1`, `yes`, `on` for true; `false`, `0`, `no`, `off` for false.

---

## Section: `[executables]`

Maps a client name to the path (or bare command name) used to launch it. Provides a persistent default for the per-call `--executable` flag. Useful for installations not on `PATH` or for pinning a specific build.

```ini
[executables]
claude = /opt/claude/bin/claude
cursor = /usr/local/bin/cursor
```

Precedence per client: `--executable` flag > `[executables]` config entry > adapter's own `PATH` lookup.

Unknown client names are accepted without warning — the adapter catalog is extensible, and a key is only consulted when that client is launched.

---

## `version` key

An optional key in `[defaults]` that declares which config schema version the file was written against.

```ini
[defaults]
version = 1
# … other keys …
```

The current schema version is `1`. If the key is present and does not match the current version, `gmlcache config validate` emits a warning. If the key is absent, no warning is emitted — existing config files without the key remain valid.

The key is **not** read during normal command execution; it is checked only by `gmlcache config validate`. It exists so that future breaking schema changes can produce a clear diagnostic ("this config was written for schema version 1; the current schema is version 2") rather than silent misbehaviour.

---

## Precedence order

For every setting except `store`, the resolution order is:

```
CLI flag  →  environment variable  →  config file  →  built-in default
```

`store` is the deliberate exception — it resolves from the config file or the built-in default only, with **no flag and no environment override**. The store is the cache's own internal structure, not a per-call knob. To run a fully isolated cache, point `GMLCACHE_CONFIG` at a different config file (its `store` key selects a separate store).

`trust_scan`, `max_size`, `max_age`, and `adapters` have no CLI flag — they are standing, deliberate choices made in config or via environment.

`gmlcache config show` displays each key's current value alongside the source that set it (`flag`, `env`, `config`, or `default`).

---

## Config file location

Override the file path entirely with `GMLCACHE_CONFIG=/path/to/config.ini`.
Otherwise the default is:

- **Windows** — `%APPDATA%\generic-ml-cache\config.ini`
- **otherwise** — `$XDG_CONFIG_HOME/generic-ml-cache/config.ini` (or `~/.config/generic-ml-cache/config.ini`)

The default `store` resolves to the per-user data directory:

- **Windows** — `%LOCALAPPDATA%\generic-ml-cache\store`
- **otherwise** — `$XDG_DATA_HOME/generic-ml-cache/store` (or `~/.local/share/generic-ml-cache/store`)

The encryption token (`GMLCACHE_TOKEN`, or the `--token` flag) is **not** a config setting — a secret never belongs in a config file. It is read only from the environment or the flag, at runtime.

Color output follows the standard `NO_COLOR` convention and is suppressed when output is not a terminal.

---

## Validating and inspecting

### `gmlcache config validate`

Parses the config file and reports all errors and warnings. Does not run any cache operation; safe to call in CI.

```bash
gmlcache config validate          # text output; exits 0 on clean, 4 on any error
gmlcache config validate --json   # structured JSON output
```

JSON output shape:

```json
{
  "config_path": "/home/user/.config/generic-ml-cache/config.ini",
  "present": true,
  "valid": false,
  "issues": [
    {"severity": "error",   "key": "mode",    "message": "invalid value 'bogus'; expected one of …"},
    {"severity": "warning", "key": "version", "message": "config schema version '0' does not match …"}
  ]
}
```

A missing config file is not an error — it exits 0 with a note that defaults apply.

### `gmlcache config show`

Displays the fully resolved configuration — every key, its value, and the source that set it — without executing any cache operation.

```bash
gmlcache config show             # human-readable table
gmlcache config show --resolved  # same (flag accepted for discoverability)
gmlcache config show --json      # machine-readable JSON
```

JSON output shape:

```json
{
  "config_path": "/home/user/.config/generic-ml-cache/config.ini",
  "loaded": true,
  "settings": {
    "mode":    {"value": "cache",  "source": "default"},
    "timeout": {"value": 30.0,     "source": "env"},
    "store":   {"value": "/data/store", "source": "config"}
  },
  "executables": {"claude": "/opt/bin/claude"}
}
```

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
