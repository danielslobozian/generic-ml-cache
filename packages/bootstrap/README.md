# generic-ml-cache-bootstrap

#### The composition root and plugin discovery for gmlcache

The startup layer that assembles the application. It discovers the
`gmlcache.adapters` plugins (whitelisting them at load time and judging which
distributions are trusted), then wires the [core](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/core)
use cases to the concrete [adapters](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/adapters)
and hands the drivers a ready application API.

It is the one place allowed to import both `core` and `adapters` — the
composition root in hexagonal terms. The drivers
([cli](https://github.com/danielslobozian/generic-ml-cache/tree/main/packages/cli),
daemon) depend on `core` + `bootstrap` only; they never import an adapter
directly. An adapter never imports `bootstrap` (that would be a leaf calling the
composition root).

## Install

You normally get it transitively (`pip install generic-ml-cache-cli` pulls it
in). Installed on its own:

```bash
pip install generic-ml-cache-bootstrap
```

## License

Apache-2.0 — see [`LICENSE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/LICENSE)
and [`NOTICE`](https://github.com/danielslobozian/generic-ml-cache/blob/main/NOTICE).
