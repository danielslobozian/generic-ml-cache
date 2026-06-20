<div align="center">

# Use Case: CI/CD and Repeated Pipelines

<sub>Use cases</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> This page explains when the pattern is useful and how it relates to gmlcache’s exact replay model.

Detached ML calls may appear in generated-code checks, documentation pipelines,
quality gates, or evaluation jobs.

gmlcache helps when repeated pipeline executions submit the same execution request.
It can also help when requests do not hit the cache by exposing usage and cache
performance.

A common diagnostic pattern:

1. A pipeline has poor hit ratio.
2. `stats` or future session reports show repeated misses.
3. Inspection reveals an unstable input such as a timestamp or generated nonce.
4. The caller removes that unstable value from the cache-relevant request.
5. Hit ratio improves.

The cache does not fix unstable inputs automatically. It makes them visible.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
