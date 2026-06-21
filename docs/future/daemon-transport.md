<div align="center">

# Future: Daemon Transport

<sub>Future direction</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!NOTE]
> This document describes planned direction. It should be read as design intent, not as a guarantee that the feature already exists.

Daemon mode should expose the same execution engine through a resident process.

It should not create a separate cache model.

The daemon can add:

- live event delivery,
- HTTP or local API access,
- shared process state,
- easier integration for multiple callers.

The underlying execution concepts remain execution request, adapter, execution record,
scope, session, and report.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
