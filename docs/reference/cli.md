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
- [Current command options](#current-command-options)
- [Future scope/session commands](#future-scopesession-commands)
- [Detached executions](#detached-executions)
- [API adapters](#api-adapters)
- [Alias mode](#alias-mode)

---

This reference contains the intended command surface. Exact syntax may differ by
release; use `gmlcache --help` for the installed version.

## Current commands

```text
gmlcache run ...
gmlcache alias <client> -- <native args...>
gmlcache check ...
gmlcache list
gmlcache inspect <key-or-prefix>
gmlcache tags
gmlcache export
gmlcache encrypt
gmlcache decrypt
gmlcache rotate
gmlcache invalidate
gmlcache session start
gmlcache session report <id>
gmlcache purge <key>
gmlcache execution status <id>
gmlcache stats
gmlcache doctor
gmlcache models <client>
gmlcache status
gmlcache init
```

<div align="center">
<img src="../images/gmlcache-help.gif" alt="gmlcache --help: the banner and the full command overview" width="760">
</div>

## Current command options

The two core commands are `run` (execute or replay a call) and `check` (forecast
cache behavior for a call without running it). `--client` is required on both;
provide a prompt with either `--prompt` or `--prompt-file`.

### `run`

Selection:

| Option | Meaning |
|---|---|
| `--client` | Adapter to use. CLI adapters (`claude`, `codex`, `cursor`) launch a local binary. API adapters (`anthropic`, `openai`, `gemini`) call the provider's REST API directly — set the corresponding `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`. Required. |
| `--model` | Model identifier, passed or translated by the adapter. |
| `--effort` | Reasoning effort (optional); omit for the client's default. For Cursor, leave this off when the model id already encodes effort. |

Input:

| Option | Meaning |
|---|---|
| `--prompt` / `--prompt-file` | The prompt, inline or from a file. |
| `--context` / `--context-file` | Context text, inline or from a file. |
| `--system-prompt` / `--system-prompt-file` | System prompt, inline or from a file. |
| `--input-file` | A file the client reads in place; its content is fingerprinted into the key and the client is granted read access. Repeatable, any type. The key watches content, not the name. |
| `--allow-path` | A folder the client may scan/read but whose contents the cache cannot fingerprint. Declaring any allow-path makes the call run fresh and store nothing (non-cacheable). Repeatable. |
| `--tag` | Label this execution for grouping and later queries (`list --tag`, `export --tag`, `tags`). Metadata only — never part of the cache key; relabeling an already-cached input accumulates tags. Repeatable. |

Capability and passthrough:

| Option | Meaning |
|---|---|
| `--grant` | Open a capability for the client: `net`, `read`, `write`, `shell`, or `web-search` — enablement, not restriction. Keyed into the call (a granted call is its own execution) and cacheable; use `--force` for a live re-fetch. Repeatable. See [Grants reference](grants.md). |
| `--client-arg` | An extra argument appended verbatim to the client launch — an escape hatch for client features the cache does not model. Part of the key; only its fingerprint is stored, never the raw value. Repeatable; order is significant. Use the `=` form for dash-leading values: `--client-arg=--flag`. |
| `--executable` | Override the client executable (the seam). |
| `--token` | Encryption token for an encrypted store (or set `GMLCACHE_TOKEN`). Needed to read or record when encryption is on; ignored on a public store. |
| `--session` | Group this run under a session id (or set `GMLCACHE_SESSION`); see [Sessions](#sessions). Journal metadata, never part of the key. |
| `--detach` | Submit the run as a background job: print an execution id and return immediately. See [Detached executions](#detached-executions). Managed-only. |

Mode:

| Option | Meaning |
|---|---|
| `--mode` | Resolution mode: `cache` (default — hit replays, miss records), `offline` (replay only; a miss is an error), or `refresh` (always call and overwrite). Falls back to config/environment. |
| `--offline` | Shortcut for `--mode offline`. |
| `--force` | Shortcut for `--mode refresh`. |
| `--persist` | How much to keep on disk: `meter` (usage/metadata only — every call runs, never replays), `cache` (default — also stores the output and replays on a hit), or `dataset` (also stores the input, to build an exportable `(input, output)` corpus). Falls back to config (`persist`) / environment (`GMLCACHE_PERSIST`). |
| `--record-on-error` | Also cache a call that fails (non-zero exit); the default stores only successes. |

Output and control:

| Option | Meaning |
|---|---|
| `--json` | Emit a machine-readable JSON envelope (status, exit, files, normalized usage, stdout) instead of the raw answer — for a parent process such as the workflow engine reading usage. Files are still written to the cwd. |
| `--stream` | Write a live NDJSON progress stream as the call runs — display-only, it never changes what is recorded. Give a path, or pass `--stream` alone to write `./gmlc-stream.jsonl`. |
| `--timeout` | Seconds before the real call is killed. |
| `-v`, `--verbose` | Print cache diagnostics to stderr (breaks exact fidelity). |

### `check`

`check` forecasts whether a call would hit or miss and what it would cost, without
executing. It accepts the same call-defining options as `run` so the forecast
matches the run you would make: `--client`, `--model`, `--effort`, `--prompt` /
`--prompt-file`, `--context` / `--context-file`, `--input-file`, `--allow-path`,
`--client-arg`, `--grant`, and `--json`. It does not take the execution-only
options (`--mode` / `--offline` / `--force`, `--stream`, `--record-on-error`,
`--executable`, `--timeout`, `--system-prompt`, `--verbose`).

### Other commands

| Command | Options |
|---|---|
| `inspect <key-or-path>` | `--raw` also prints the client's verbatim usage block. Accepts a short key as shown by `list`. Shows whether the entry's input was stored (`dataset` depth). |
| `list` | `--client`, `--model` filter the listing; `--tag` / `--exclude-tag` filter by tag (match-any include / exclude, with exclude winning); `--json` for machine output. |
| `tags` | List the distinct tags in use across current executions, with counts. `--json` for machine output. |
| `export` | Export the `dataset`-depth `(input, output)` corpus as JSONL. `--tag` / `--exclude-tag` filter by tag (match-any; exclude wins); `-o` / `--output FILE` writes to a file instead of stdout (a per-record summary still goes to stderr). Entries stored below `dataset` depth carry no input and are skipped (and reported). On an encrypted store it needs `--token` / `GMLCACHE_TOKEN`. |
| `models <client>` | `--executable` overrides the client executable; `--timeout`; `--json`. Omit `<client>` to query every registered client. |
| `doctor` | `--timeout` (default 10s); `--json`. |
| `stats` | Shows total store size and, when `max_size` is configured, quota fill level. `--json`. |
| `status` | `--json`. Also shows the encryption state (public / encrypted). |
| `init` | (no options) writes a starter config file on explicit request. |
| `purge` | `<key>`, `--tag <tag>`, `--session <id>`, or `--all` selects the target (mutually exclusive). `--hard` hard-deletes (default: soft purge — frees blobs, keeps statistics). `--all` requires `--confirm "purge all"` (soft) or `--confirm "hard delete all"` (hard). `--json` for machine output. |

<div align="center">
<img src="../images/gmlcache-purge.gif" alt="gmlcache purge: stats shows store size; purge --tag frees blobs; purge --all with confirmation phrase empties the store" width="760">
</div>

### Encryption

At-rest encryption is **store-wide** and optional. gmlcache generates the token (no outside
passwords); keep it safe — it is shown once and is unrecoverable if lost.

<div align="center">
<img src="../images/gmlcache-encrypt.gif" alt="gmlcache encrypt: record into a public store, encrypt it (token shown once), then the store is locked without the token" width="760">
</div>

| Command | Options |
|---|---|
| `encrypt` | Enable encryption: generate a token, encrypt the store, print the token once. |
| `decrypt` | Disable encryption (decrypt back to plaintext). `--token` / `GMLCACHE_TOKEN`. |
| `rotate` | Swap to a freshly generated token (the content is not re-encrypted). `--token` is the *current* token. |
| `invalidate` | Crypto-shred the store — the escape when the token is lost. Requires `--yes`. |

The token is supplied at runtime via `--token` or `GMLCACHE_TOKEN`, **never the config file**.
Content commands (`run`, `export`) need it on an encrypted store; metadata-only commands
(`list`, `stats`, `tags`, `status`) do not. Encryption covers the content (prompts, outputs,
inputs); execution metadata stays plaintext — see the
[data-handling note](../design/data-handling.md).

### Sessions

A session groups one workflow's runs so they can be reported together. Sessions are
single-user and need only a generated id — no token.

| Command | Options |
|---|---|
| `session start` | Generate a new session id and print it (scriptable: `SESSION=$(gmlcache session start)`). |
| `session report <id>` | Roll up the session: headline counts + day span, token usage **by provider/model** (spent + saved-by-hit), and **per-day** activity. Tokens stay next to their model; no dollar figures. `--json` for the structured report. |

Attach a run to a session with `run --session <id>` or `GMLCACHE_SESSION`. The session id is
journal metadata, never part of the cache key, and sessions span every run kind. Reporting is
metadata-only, so it works on an encrypted store without the token.

## Future session commands

```text
gmlcache session watch <session-id>
```

`session watch` (a live tail of a running session) is not yet built; `session start` and
`session report` have shipped — see [Sessions](#sessions) above.

## Detached executions

A managed run can be **detached**: `gmlcache run --detach` submits it as a background job,
prints an **execution id**, and returns immediately. The work continues in a separate,
OS-detached worker process and is recorded into the normal cache; a detached run **never**
writes generated files to your cwd (the launch has already returned).

```text
gmlcache run --detach ...                                  # submit; prints an execution id
gmlcache execution status <id>                             # state, timings, exit, result key
gmlcache execution watch <id>                              # replay the event log; follow if live
gmlcache execution result <id>                             # the finished job's output
gmlcache execution materialize <id> --output-dir <path>    # write its generated files on demand
gmlcache execution list                                    # all jobs and their states
```

<div align="center">
<img src="../images/gmlcache-async.gif" alt="gmlcache run --detach returns an execution id immediately; execution status / watch / result follow the background job to its recorded result" width="820">
</div>

State lives under `<store>/jobs/`. A per-job **liveness lock** (SQLite, released by the OS when
the worker's process dies) lets a reader tell a *live* worker from one that *vanished* mid-run —
the latter reads as **interrupted**, so `status` / `watch` never hang on a dead worker. `watch`
replays the durable event log from the start (a late watcher still sees every event in order),
then follows it live — the worker's lifecycle interleaved with the client's own live progress
(`run.start`, `thinking`, `tool`, `result`, `run.end`), the same stream `run --stream` produces.
`--json` is on `status` and `list`. Detach is **managed-only**. On an
**encrypted** store, pass `--token` / `GMLCACHE_TOKEN` to `run --detach`: it is handed to the
worker through its environment (never written to disk), and `result` / `materialize` take
`--token` to decrypt — `status` / `watch` / `list` need none (job metadata is plaintext).

## API adapters

The `anthropic`, `openai`, and `gemini` clients call the provider's HTTP API directly —
no local binary needed. Set the appropriate key in the environment, then use `run` as normal:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
gmlcache run --client anthropic --model claude-haiku-4-5-20251001 --prompt "..."

export OPENAI_API_KEY=sk-...
gmlcache run --client openai --model gpt-4.1-mini --prompt "..."

export GEMINI_API_KEY=AIza...
gmlcache run --client gemini --model gemini-2.0-flash --prompt "..."
```

The same prompt sent to different providers produces separate cache entries (the client name
is part of the key). Repeating the same call to the same provider is an instant replay.

<div align="center">
<img src="../images/gmlcache-api.gif" alt="gmlcache run --client anthropic/openai/gemini: three providers, one prompt — first call is a live REST request, repeat is an instant cache hit" width="860">
</div>

API adapters support `--model`, `--effort`, `--tag`, `--session`, `--mode`, `--persist`,
and `--json`. They do not support `--grant`, `--client-arg`, or `--input-file` (no subprocess
sandbox). `gmlcache models <client>` queries the provider's model list live.

## Alias mode

A thin native-client wrapper: run a client through the cache while writing its
command line yourself. gmlcache models nothing — everything after the client is an
**opaque tail**, forwarded to the client verbatim and keyed (by fingerprint) as the
cache identity.

```text
gmlcache alias <client> -- <native args...>
gmlcache alias claude -- -p "hello" --model opus    # caches a raw claude call
alias claude='gmlcache alias claude'                # drop-in: claude -p "hi" is now cached
```

gmlcache's own options come **before** the client; everything after the client is
native. A leading `--` separator is optional — it keeps a dash-leading tail from
fighting the parser, and is stripped before forwarding.

| Option (before the client) | Meaning |
| --- | --- |
| `--mode` / `--offline` / `--force` | resolution mode (default `cache`; shortcuts for `offline` / `refresh`). |
| `--persist` | `meter` / `cache` (default) / `dataset`. At `dataset` the native arg vector is the stored input. |
| `--record-on-error` | keep a failed call as history (a failure is **never** served as a hit). |
| `--executable` | override the client executable (the seam). |
| `--token` | encryption token for an encrypted store (or `GMLCACHE_TOKEN`). |
| `--session` | group this run under a session id (or `GMLCACHE_SESSION`). |
| `--timeout` | seconds before the real call is killed. |

A replay reproduces the native call's stdout, stderr and exit code. Unlike a managed
`run`, alias mode does **no** isolation and **no** file capture: generated files are
written by the live call only — there is nothing to materialize on a hit. Alias mode is
for users who want native client behavior plus basic caching; reach for `run` when you
want input fingerprinting, generated-file replay, grants, or detached execution.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
