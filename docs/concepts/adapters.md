<div align="center">

# Adapters

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

Adapters translate gmlcache execution requests into concrete backend calls.

Today the supported backends are detached CLI clients. Future adapters may target
provider APIs. The execution engine should treat both as adapters.

## Adapter responsibilities

An adapter may own:

- command construction,
- prompt delivery,
- model/effort translation,
- grant translation,
- structured output parsing,
- usage extraction,
- answer extraction,
- client-specific error behavior.

## Adapter differences

Not all adapters support the same features. Grants, effort levels, model listing,
usage reporting, and cost reporting can differ.

The common engine should expose a stable execution model. Adapter-specific
behavior should stay in adapter code and reference documentation.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
