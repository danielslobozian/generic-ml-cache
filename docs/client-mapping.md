<div align="center">

# Client Mapping

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

Adapters translate gmlcache execution requests to backend-specific mechanics.

This document should be updated whenever adapter behavior changes.

## Common request fields

| gmlcache field | Meaning |
|---|---|
| adapter/client | Backend adapter to launch |
| model | Model identifier passed or translated by the adapter |
| effort | Reasoning/effort level where supported |
| prompt/context | Text sent to the adapter |
| input files | Files fingerprinted and granted for reading |
| allow paths | Paths the adapter may scan; not cacheable by default |
| grants | Declared capabilities such as network/shell/read/write |
| client args | Opaque passthrough arguments included in the key |

## Adapter differences

Adapters differ in prompt delivery, model naming, grant mechanics, structured
output, and usage reporting. Those differences live in the adapter code; the
engine stays adapter-agnostic.

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
