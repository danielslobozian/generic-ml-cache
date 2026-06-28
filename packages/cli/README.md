<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-lockup-dark.png">
  <img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-lockup.png" alt="gmlcache" width="300">
</picture>
</p>

#### Detached ML Execution Cache — the terminal client

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-2563eb?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-d97706?style=flat-square)](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/ROADMAP.md)

`gmlcache` runs, records, and replays detached ML workloads — record a real client (or API)
call once, replay it forever by its content key, offline and byte-for-byte.

> **Single-user, local — not a gateway.** gmlcache runs on your machine, as you, across the
> subscriptions and APIs you already hold. It is **not** a multi-user router and **not** a way
> to share one subscription — see
> [Positioning](https://github.com/danielslobozian/generic-ml-cache/blob/main/docs/design/positioning.md).

## Install

```bash
pip install generic-ml-cache-cli          # gmlcache command + the engine
```

---

## run and check — record and replay

`run` calls the real client on a miss and replays from cache on a hit.
`check` forecasts the result without calling anything.

```bash
gmlcache run   --client claude --model sonnet --prompt "Write a haiku about caching."
gmlcache check --client claude --model sonnet --prompt "Write a haiku about caching."
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-demo.gif"
     alt="gmlcache: check (miss) → run (records the real call) → check (hit) → run (instant cache replay)"
     width="760">
</p>
<p align="center"><sub>Same command twice: the first call runs the real client; the second is served from cache, instantly and byte-identical.</sub></p>

---

## Detached executions — `--detach`

`run --detach` returns an execution id immediately.
`execution watch` follows the client's live progress (thinking, tool calls) to the result.

```bash
JID=$(gmlcache run --client claude --model sonnet --grant web-search \
          --prompt "Search for the capital of France and write a haiku." --detach)
gmlcache execution status $JID
gmlcache execution watch  $JID   # streams the client's live progress
gmlcache execution result $JID   # fetch the recorded result
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-async.gif"
     alt="gmlcache run --detach returns an id; execution watch streams the client's live thinking and tool calls to the result"
     width="760">
</p>

---

## Browse the store — `list`, `inspect`, `stats`, `tags`

Inspect what is in the cache at any time.

```bash
gmlcache list                  # all stored executions (key, client, model, state)
gmlcache list --tag tutorial   # filter by tag
gmlcache tags                  # all tags in the store
gmlcache stats                 # execution count, hit count, store size
gmlcache inspect <key>         # full detail for one execution
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-inspect.gif"
     alt="gmlcache list, tags, stats, and inspect showing a stored execution in full detail"
     width="760">
</p>

---

## Sessions

Group a workflow's runs into a named session and roll up usage by provider/model.

```bash
export GMLCACHE_SESSION=$(gmlcache session start --tag sprint-3)
gmlcache run --client claude --model sonnet --prompt "…"
gmlcache run --client claude --model sonnet --prompt "…"   # cache hit
gmlcache session report $GMLCACHE_SESSION                  # hits, tokens, cost saved
gmlcache session report --tag sprint-3                     # aggregate across all sprint-3 sessions
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-sessions.gif"
     alt="session start with a tag, two runs (one cache hit), session report, aggregate report by tag"
     width="760">
</p>

### Session exec spec and tag management (0.13.0)

Pin an adapter, model, and effort to a session.
Add and remove tags at any time.

```bash
SESSION=$(gmlcache session start --client anthropic --model claude-haiku-4-5-20251001 --effort low --tag sprint-4)
gmlcache session tag --add    $SESSION experiment   # add a tag
gmlcache session tag --remove $SESSION sprint-4     # remove a tag
gmlcache session update $SESSION --client openai --model gpt-4.1-mini --effort medium
gmlcache session clear-spec $SESSION
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-session-spec.gif"
     alt="session start with exec spec, tag add/remove, session update, session clear-spec"
     width="760">
</p>

---

## API adapters

Call Anthropic, OpenAI, and Gemini directly via REST — no CLI binary required.

```bash
gmlcache run --client anthropic --model claude-haiku-4-5-20251001 --prompt "What is a content-addressed cache?"
gmlcache run --client openai    --model gpt-4.1-mini              --prompt "What is a content-addressed cache?"
gmlcache run --client gemini    --model gemini-2.0-flash           --prompt "What is a content-addressed cache?"
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-api.gif"
     alt="gmlcache run against Anthropic, OpenAI, and Gemini — first calls are live, repeating any prompt is an instant cache hit"
     width="760">
</p>

---

## Purge

Reclaim space. Purge is *soft* by default — execution records and statistics are kept;
only the stored blobs are freed. `--all` wipes everything.

```bash
gmlcache purge --tag demo        # soft-purge by tag
gmlcache purge --key <key>       # soft-purge one execution
gmlcache purge --all --confirm 'purge all'   # wipe the entire store
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-purge.gif"
     alt="purge --tag frees blobs while keeping execution records; purge --all wipes the store"
     width="760">
</p>

---

## Export

Export tagged executions as an `(input, output)` JSONL dataset.

```bash
gmlcache export --tag eval -o dataset.jsonl
gmlcache export --tag eval --include-tag verified -o dataset.jsonl
```

---

## Encryption

Encrypt the whole store at rest. gmlcache generates a token — keep it; without it the
cache is unreadable even to gmlcache itself.

```bash
gmlcache encrypt                                    # lock the store; prints the token once
GMLCACHE_TOKEN=<token> gmlcache run --client …     # unlock on the fly for a single run
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-encrypt.gif"
     alt="gmlcache encrypt locks the store; running without the token fails; the token re-enables replay"
     width="760">
</p>

---

## Daemon (0.13.0)

Start a local HTTP API over the cache store. Exposes every CLI capability as REST
endpoints — useful for scripts, CI pipelines, and IDE integrations.

```bash
gmlcache daemon start            # foreground on 127.0.0.1:8765
gmlcache daemon start --port 9000 --session abc --metrics
gmlcache daemon status           # health check
gmlcache daemon stop             # SIGTERM
```

Hit the API directly:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/stats
curl -X POST http://127.0.0.1:8765/sessions -H 'Content-Type: application/json' \
     -d '{"tags": ["ci-run-42"]}'
```

Or point any Anthropic SDK client at the cache-transparent gateway:

```python
import anthropic
client = anthropic.Anthropic(api_key="…", base_url="http://127.0.0.1:8765/gateway/claude")
```

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-daemon.gif"
     alt="gmlcache daemon start, curl /health /info /executions /stats, create session via API, daemon stop"
     width="760">
</p>

---

## Command overview — `--help`

<p align="center">
<img src="https://raw.githubusercontent.com/danielslobozian/generic-ml-cache/main/docs/images/gmlcache-help.gif"
     alt="gmlcache --help: the banner and the full command menu"
     width="620">
</p>

---

## Built on a reusable engine

`gmlcache` is one inbound driver over
[`generic-ml-cache-core`](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/core)
— the stateless engine that ships the domain model, use cases, ports, and every adapter.
Embed it directly instead of driving it from a terminal:

```python
from generic_ml_cache_core import build_use_cases

wired = build_use_cases(store_root="/path/you/choose")
execution = wired.run_ml.execute(command)
```

## Links

- **Repository & docs:** <https://github.com/danielslobozian/generic-ml-cache>
- **Changelog:** [`CHANGELOG.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/CHANGELOG.md)
- **Security policy:** [`SECURITY.md`](https://github.com/danielslobozian/generic-ml-cache/blob/main/SECURITY.md)

## License

Apache-2.0 — see [`LICENSE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
and [`NOTICE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/NOTICE).
