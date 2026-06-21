<div align="center">

# Executions

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Contents](#contents)
- [Generated files](#generated-files)
- [Usage metadata](#usage-metadata)
- [Where it is stored](#where-it-is-stored)

---

An **execution** is the record of one detached call — what was asked, and what came
back. It holds enough to inspect the call and replay its observable result without
calling the underlying adapter again.

A successful execution is what a cache *hit* replays. Failed and superseded
executions are retained too (an append-only history), but only a current, successful,
persisted execution answers a hit.

## Contents

An execution records:

- its **call identity** — what uniquely identifies the call: the adapter/client,
  model, and effort, plus *fingerprints* of the prompt, context, declared input
  files, client arguments, and grants. Only fingerprints are stored — never the raw
  prompt or context (see [transparency](#where-it-is-stored)).
- the **kind** (managed-local, passthrough, or API) and **state** (success or failed),
- **stdout**, **stderr**, and the **exit code**,
- **generated files**,
- **token usage** when the client reports it,
- a **failure detail** when the call failed.

## Generated files

Generated files are first-class execution content.

A detached ML call may produce useful work by writing files rather than printing to
stdout. Caching only stdout would lose that work. gmlcache therefore records files
created or modified inside the isolated execution folder and can replay or materialize
them later, byte-for-byte.

## Usage metadata

An execution can include normalized usage fields and the adapter's raw usage block.
Unknown values remain unknown (never coerced to zero). Client-reported cost is recorded
as an estimate, not authoritative billing.

## Where it is stored

The execution's **structure** — its identity, kind, state, usage, and the references to
its output — lives in a SQLite **execution repository**. The output **bytes** (stdout,
stderr, generated files) live in a content-addressed **blob store**, referenced by key;
identical bytes are stored once. See [Storage](../storage.md).

Nothing the cache reads is more than it must: inputs are fingerprinted at the edge, and
**only those fingerprints are persisted** — never raw prompts, context, or messages.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
