# generic-ml-cache-daemon

The HTTP daemon for [generic-ml-cache](https://github.com/danielslobozian/generic-ml-cache).
Exposes the cache store and all session/execution functionality as a local REST API with
server-sent event (SSE) streaming, plus a caching proxy gateway for the Anthropic Messages API.

## Installation

```bash
pip install generic-ml-cache-daemon           # runtime only
pip install "generic-ml-cache-daemon[metrics]" # + Prometheus /metrics endpoint
```

## Starting the daemon

```bash
python -m generic_ml_cache_daemon             # uses defaults
GMLCACHE_STORE=/path/to/store python -m generic_ml_cache_daemon
GMLCACHE_SESSION=abc GMLCACHE_METRICS=1 python -m generic_ml_cache_daemon
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `GMLCACHE_STORE` | config store path | Path to the cache store directory |
| `GMLCACHE_SESSION` | *(none)* | Bind all intercepted calls to a session |
| `GMLCACHE_METRICS` | `0` | Set `1` to enable the Prometheus `/metrics` endpoint |

## HTTP API

The daemon listens on `http://127.0.0.1:8765` by default.
Interactive API docs are available at `/docs` (Swagger UI) and `/redoc`.

### Observability

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness: `{"status":"ok"}` |
| `GET` | `/ready` | Readiness: probes the store; 503 if inaccessible |
| `GET` | `/info` | Version, store path, adapters, bound session |
| `GET` | `/metrics` | Prometheus text (requires `[metrics]` extra + `--metrics`) |

### Sessions

| Method | Path | Description |
|---|---|---|
| `GET` | `/sessions` | List all session IDs |
| `POST` | `/sessions` | Create a session (body: `{tags, spec}`) |
| `GET` | `/sessions/{id}` | Get session tags and spec (404 if unknown) |
| `GET` | `/sessions/{id}/stats` | Calls, hits, hit rate |
| `PUT` | `/sessions/{id}/spec` | Set or replace execution spec |
| `DELETE` | `/sessions/{id}/spec` | Remove execution spec |
| `POST` | `/sessions/{id}/tags` | Add a tag |
| `DELETE` | `/sessions/{id}/tags/{tag}` | Remove a tag |

### Executions & Global Stats

| Method | Path | Description |
|---|---|---|
| `GET` | `/executions` | List all current (servable) executions |
| `GET` | `/executions/{key}` | Inspect by exact key or prefix (409 on ambiguous prefix) |
| `GET` | `/stats` | Global execution count + event counts |
| `POST` | `/purge` | Purge by scope: `all`, `key`, `tag`, `session`, `session_tag` |

**Purge body examples:**

```json
{"by": "all"}
{"by": "key", "target": "deadbeef"}
{"by": "session", "target": "abc123"}
```

### Run (synchronous or SSE)

```
POST /run
{
  "client": "anthropic",
  "model": "claude-opus-4-8",
  "prompt": "Summarise the paper.",
  "effort": "medium",
  "session_id": "abc"
}
```

- `Accept: application/json` (default) — blocks and returns `{execution_key, state, cache_hit, stdout, stderr}`
- `Accept: text/event-stream` — SSE: `{"type":"accepted"}` immediately, then `{"type":"complete", ...}` on finish

### Jobs (detached / async)

| Method | Path | Description |
|---|---|---|
| `POST` | `/jobs` | Submit a background execution; returns `{job_id, state}` with 202 |
| `GET` | `/jobs` | List all job IDs |
| `GET` | `/jobs/{id}` | Poll state: `pending`, `running`, `done`, `error` |
| `GET` | `/jobs/{id}/stream` | SSE: periodic `status` events, then `complete` or `error` |

### Claude Gateway

```
POST /gateway/claude/v1/messages
```

A cache-transparent proxy for the Anthropic Messages API. Requests that hit the
cache are returned without a network call to Anthropic. The response shape matches
the Anthropic Messages API exactly, with one extra field: `x_cache_hit: bool`.

**Limitations (0.13.0):** single-turn conversations only (one `role: user` message,
no prior assistant turns). Multi-turn support is planned.

**Example:**

```bash
curl http://127.0.0.1:8765/gateway/claude/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Hello, world!"}],
    "max_tokens": 256
  }'
```

Point any Anthropic SDK client at the gateway by overriding the base URL:

```python
import anthropic

client = anthropic.Anthropic(
    api_key="...",
    base_url="http://127.0.0.1:8765/gateway/claude",
)
```

## Architecture

The daemon is a thin FastAPI layer over the `generic-ml-cache-core` hexagonal
architecture. It does not own any state — all persistence goes through the
existing `JournalMetrics` (SQLite registry) and `ExecutionRepository`
that the core library manages.

Background jobs run in a `ThreadPoolExecutor` inside an in-process
`JobRegistry`; job state is not persisted across daemon restarts.

## License

Apache-2.0
