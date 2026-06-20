<div align="center">

# Execution Requests

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

An execution request is the complete description of detached ML work sent to
gmlcache.

It is the primary abstraction of the system.

## Why not “prompt”?

The prompt is only one part of a call. The same prompt can produce different
results when any of the following change:

- adapter,
- model,
- effort,
- context,
- input files,
- grants,
- passthrough arguments,
- execution mode.

Therefore the cache key is built from the execution request, not from the prompt
alone.

## Request fields

A full execution request can include:

- adapter/client name,
- model,
- effort or reasoning level,
- prompt,
- context,
- declared input files,
- allow paths,
- scan-trust choice,
- grants,
- passthrough client arguments,
- record/cache/refresh/offline mode,
- future scope/session/detach metadata.

Only fields that can affect execution semantics belong to cassette identity.
Observability metadata, such as future session IDs, must not change cache
identity.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
