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
  -> key / cacheability decision
  -> hit:  replay the stored execution
  -> miss: run the adapter
  -> record a new execution when allowed
  -> note the access event
```

The engine should not contain adapter-specific launch mechanics. Those belong in
adapters.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
