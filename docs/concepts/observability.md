<div align="center">

# Observability

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Current observability](#current-observability)
- [Future observability](#future-observability)
- [Rule](#rule)

---

Observability is a first-class capability of gmlcache.

Replay is one source of value. Observability is another.

Even when an execution misses the cache, gmlcache can still record what happened:
which adapter ran, which model was used, what usage was reported, whether files
were generated, how often a cassette was replayed, and what cost estimate the
client exposed.

## Current observability

Today, observability appears through:

- `stats`,
- `list`,
- `inspect`,
- cassette metadata,
- access registry events,
- normalized usage envelopes.

## Future observability

Future scopes and sessions extend the same model:

```text
Scope
  owns Sessions

Session
  observes Executions

Execution
  records or reuses Cassettes
```

A session report can show workflow-level usage and cache effectiveness. A scope
report can aggregate many sessions.

## Rule

Observability must never change execution behavior.

Reports can describe. They must not decide cassette identity.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
