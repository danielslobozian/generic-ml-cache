<div align="center">

# Use Case: Workflow Engines

<sub>Use cases</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> This page explains when the pattern is useful and how it relates to gmlcache’s exact replay model.

A workflow engine can use gmlcache as a detached ML execution layer.

The engine submits execution requests, uses `check` to forecast cache behavior,
uses `run` to execute or replay, and consumes JSON output for usage and result
metadata.

Future sessions provide a natural workflow boundary: one workflow run can map to
one gmlcache session. Future async execution allows the workflow engine to submit
work, watch events, and materialize results explicitly.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
