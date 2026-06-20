<div align="center">

# Design

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

> [!IMPORTANT]
> This document is normative for the current documentation set. Preserve its meaning when editing related pages.

## At a glance

- [Identity](#identity)
- [The central abstraction: execution request](#the-central-abstraction-execution-request)
- [Dumbness means non-interpretation](#dumbness-means-non-interpretation)
- [Sound replay over high hit rate](#sound-replay-over-high-hit-rate)
- [Isolation is correctness](#isolation-is-correctness)
- [Generated files are first-class](#generated-files-are-first-class)
- [Adapters, not special cases](#adapters-not-special-cases)
- [Observability is a pillar](#observability-is-a-pillar)
- [Scopes and sessions are metadata](#scopes-and-sessions-are-metadata)
- [Daemon is transport](#daemon-is-transport)
- [Development principle](#development-principle)

---

## Identity

gmlcache is a Detached ML Execution Platform.

It records and replays detached ML executions through adapters. The cache is
exact and content-addressed, but the project is broader than a stdout cache: it
also records generated files, preserves usage metadata, exposes inspection and
statistics, and provides a foundation for scopes, sessions, asynchronous
executions, and future daemon transport.

The project should not be presented as a replacement for an ML client, an
interactive session manager, or a hosted gateway. It is a local-first execution
and replay layer for detached work.

## The central abstraction: execution request

The cache key is derived from the execution request.

An execution request includes:

- adapter,
- model,
- effort,
- prompt and context,
- declared input files,
- allowed scan paths,
- grants,
- passthrough client arguments,
- execution mode.

The prompt alone is not the request. A prompt executed by another adapter, model,
effort, grant set, or input set is a different execution request.

## Dumbness means non-interpretation

The cache is intentionally dumb about content.

It does not read a prompt and decide what the prompt means. It does not compare
prompts semantically. It does not ask the model which files it depended on and
trust the answer. It does not decide that two different execution requests are
“similar enough”.

This does **not** mean the cache must avoid state, reporting, sessions, scopes,
or asynchronous execution. Those features live on the transport and bookkeeping
side. They must never change cassette identity or replay correctness.

The invariant is:

> Bookkeeping may describe executions, but it must not reinterpret them.

## Sound replay over high hit rate

gmlcache prefers a miss over an unsound hit.

A false miss costs another model call. A false hit can return the wrong output,
write the wrong files, or hide a real change. The cache must therefore only replay
when it can explain why the execution request matches the recorded cassette.

## Isolation is correctness

For full execution mode, the underlying client runs in a cache-owned temporary
execution folder.

That folder is not Fort Knox. It is not a security sandbox. It is an execution
workspace that makes inputs and outputs observable.

It solves three problems:

1. **Input discipline.** Declared files can be fingerprinted and included in the
   key. Declared scan paths can be handled explicitly and marked as non-cacheable
   unless the caller opts into trust.
2. **Output attribution.** Files created or modified inside the execution folder
   can be attributed to the execution by comparing before/after state.
3. **Replay.** Captured files can later be materialized as part of replay or
   result retrieval.

Folders are a useful filesystem representation, not a trust boundary. The store
may physically organize files in folders, but relationships such as scope,
session, usage, and access history belong to metadata and registry state.

## Generated files are first-class

Generated files are not an extra. They are part of the result.

Many detached ML executions produce files as their meaningful output. A cache that
only stores stdout would be simpler, but it would not faithfully replay a file-
producing execution.

A cassette records the observable result of the execution: stdout, stderr, exit
code, generated files, and usage metadata when available.

## Adapters, not special cases

The engine should be adapter-based.

Adapters translate an execution request into the mechanics required by a
particular backend. Today those backends are detached CLI clients. Future adapters
may target provider APIs. The execution model should not need to be rewritten
when a new adapter is introduced.

Adapter differences are real. They appear in model naming, effort support, prompt
delivery, grants, usage reporting, and structured output. The adapter layer owns
that translation.

## Observability is a pillar

Replay is one source of value. Observability is another.

gmlcache can be useful even when every execution misses the cache. It still gives
a caller a record of what was executed, which adapter and model were used, what
files were produced, what usage was reported, and what cost estimate the client
provided when available.

Future scopes and sessions extend that same principle from a single execution to
a workflow, namespace, or long-running body of work.

## Scopes and sessions are metadata

Future scope tokens and sessions must not participate in cassette identity.

A scope partitions cache visibility and reporting. A session groups executions for
analysis. Neither changes what the underlying client receives. Neither changes
what cassette key an execution request produces.

This keeps correctness separate from observability.

## Daemon is transport

A daemon is not required for the execution model.

Asynchronous execution can be represented locally by persisted execution state,
status, event logs, and result retrieval. A daemon may later expose the same model
through HTTP, server-sent events, websockets, or another transport, but it should
not become a second execution engine.

## Development principle

Features should be added because they serve a real need in the project’s intended
use, not because the architecture could theoretically support them.

A feature may benefit many people. That is welcome. But the project should avoid
turning into a generic hosted gateway, account system, policy engine, or security
platform merely because those things could be layered on top.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
