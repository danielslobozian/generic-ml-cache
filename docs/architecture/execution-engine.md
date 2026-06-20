<div align="center">

# Execution Engine

<sub>Architecture</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

The engine receives an execution request and decides whether it can be served
from cache, must call an adapter, or is non-cacheable.

Conceptual flow:

```text
Execution Request
  -> key/cacheability decision
  -> hit: replay cassette
  -> miss: adapter execution
  -> record cassette when allowed
  -> update registry
```

The engine should not contain adapter-specific launch mechanics. Those belong in
adapters.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
