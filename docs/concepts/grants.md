<div align="center">

# Grants

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Why grants exist](#why-grants-exist)
- [Common vocabulary](#common-vocabulary)
- [Grants and APIs](#grants-and-apis)

---

Grants declare capabilities the launched adapter may need.

Examples include network access, file access, shell execution, or other client
capabilities. Grants are not security guarantees. They are an explicit execution
request field that lets gmlcache translate caller intent into adapter-specific
launch mechanics where supported.

## Why grants exist

Detached clients often require explicit permission to write files, read outside a
workspace, use the network, or run commands. If those capabilities affect what the
client can do, they belong in the execution request.

## Common vocabulary

gmlcache should maintain a small common grant vocabulary. A grant should become
part of that vocabulary only when it has a clear cross-adapter meaning.

Adapters may support different subsets. Unsupported grants should fail clearly or
be reported as not supported rather than silently changing behavior.

## Grants and APIs

Some grants make sense mainly for local CLI clients. For example, a shell grant or
workspace write grant is not the same thing for a provider API adapter. Each
adapter must declare what it supports.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
