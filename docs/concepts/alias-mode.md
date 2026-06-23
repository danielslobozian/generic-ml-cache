<div align="center">

# Alias Mode

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Full execution mode](#full-execution-mode)
- [Alias mode](#alias-mode)
- [Why no full autocomplete initially](#why-no-full-autocomplete-initially)
- [Output model](#output-model)

---

Alias mode is a future thin-wrapper mode.

It exists because not every caller needs the full execution model. Some callers
only want native client behavior with basic caching.

## Full execution mode

Full execution mode uses gmlcache’s execution request contract:

- adapter,
- model,
- effort,
- declared inputs,
- allowed paths,
- grants,
- generated artifact capture,
- usage reporting,
- future sessions.

This mode is appropriate when the caller wants reliable artifact capture and
replay.

## Alias mode

Alias mode treats everything after the selected adapter as native adapter input.

gmlcache does not try to understand every native option. The raw native argument
tail is passed through to the adapter and included in cache identity.

Conceptually:

```text
gmlcache alias <adapter> <native adapter arguments...>
```

The native client remains responsible for errors, validation, and option parsing.

## Why no full autocomplete initially

Full autocomplete would require modeling each adapter’s native CLI surface, its
versions, and its option behavior. Alias mode can be useful without that. Treating
the native tail as opaque keeps the mode simple and honest.

## Output model

Alias mode may initially focus on stdout, stderr, and exit status. If generated
files matter, callers should prefer full execution mode.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
