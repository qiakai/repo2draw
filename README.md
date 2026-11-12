# repo2draw

English | [中文](README.zh.md)

Zero-AI architecture-diagram sync for README: a purely static analyzer
(regex + directory rules) extracts modules and their dependencies, encodes
them into an `x-cmd draw` chart URL, and writes it back between markers in
`README.md`. All diagrams render from URLs — no PNG/SVG binaries are ever
committed.

## How it works

A three-step pipeline — one script per step, with inspectable intermediate
artifacts:

1. **`scripts/analyze_arch.py`** — detects the primary language from manifest
   files, skips noisy directories (`.git`, `node_modules`, `dist`, `docs`,
   `examples`…), and extracts cross-module references from import / require /
   include statements with regexes (≤15 nodes, ranked truncation; cyclic
   imports are handled by SCC-condensed layered layout). Unknown repositories
   gracefully degrade to a directory-tree diagram. **Outputs `arch.json`
   architecture data** (nodes carry id / type / label / sub / top-level group
   / grid cell).
2. **`scripts/build_diagram.py`** — **generates the chart from `arch.json`**:
   encodes the data into the `https://x-cmd.com/draw/arch2` URL parameters
   (nodes / edges / boundary boxes / theme) and emits a Markdown image line.
   Length guard: warn above 4000 chars, refuse above 7500.
3. **`scripts/update_readme.py`** — sync only: line-anchored regex replaces
   the content between markers in `README.md`, appends a marker block at EOF
   when missing; atomic writes preserving permissions; multiple READMEs in
   one run.

The GitHub Actions workflow (`.github/workflows/sync-arch.yml`) chains the
three steps and pushes the result back: manual `workflow_dispatch` plus
automatic runs on pushes to the default branch that touch source paths
(`[skip ci]` + author check + paths allowlist — three guards against loops).

## Supported languages

| Language | Detected by | Dependency extraction |
| --- | --- | --- |
| Python | `pyproject.toml` / `requirements.txt` / `setup.py` | `import` / `from X import Y` (incl. relative imports) |
| Node.js | `package.json` | `require` / `import … from` (relative paths, `@/` aliases) |
| Go | `go.mod` | `import` blocks + module prefix (root package = one node) |
| Rust | `Cargo.toml` | `use crate::` / `mod` |
| Java / Kotlin | `pom.xml` / `build.gradle(.kts)` | `import` (package dirs expanded recursively) |
| C# | `*.csproj` / `*.sln` | `using` |
| PHP | `composer.json` | `use` (PSR-4 namespaces) / `require` |
| Ruby | `Gemfile` | `require` / `require_relative` |
| Swift | `Package.swift` | `import` (targets under Sources/) |
| C / C++ | `CMakeLists.txt` / `meson.build` | `#include "…"` (relative path resolution) |
| Other / unknown | none | directory-tree fallback (dashed edges; every repo still gets a diagram) |

## Color model (why it isn't monotonous)

Node colors in arch2 are **fixed per node type** (no per-node color override
— verified empirically):

| Type | Legend | Example keywords |
| --- | --- | --- |
| `fe` | Frontend | web, ui, pages, templates, views, render |
| `be` | Backend | api, server, routes, controllers, blueprints, services |
| `db` | Database | db, models, storage, cache, repository, dao |
| `cloud` | Cloud | deploy, infra, k8s, docker, metrics |
| `sec` | Security | auth, crypto, oauth, jwt, rbac |
| `bus` | Message bus | queue, events, workers, tasks, signals, hooks |
| `svc` | Service | default (no keyword matched) |
| `ext` | External | sdk, connector, plugins, compat, client |

On top of that, **boundary boxes** (the `b=` parameter, auto-grouped by
top-level directory, drawn only for groups with ≥2 nodes) get their own
accent colors (s8~s10), further enriching the palette. Types are derived
deterministically from module names, so the legend always stays honest.

## Examples (real-world repositories, generated in one shot)

**flask** (Python) — 15 core modules (blueprints=Backend, signals=Message
bus, templating=Frontend), src boundary box, 40 dependency edges collapsed
into clean layers by SCC:

![flask architecture](https://x-cmd.com/draw/arch2?title=flask&t=shadcn&n=app%3Bsvc%3Bapp%3Bentry%3Br1c0&n=blueprints%3Bbe%3Bblueprints%3B%3Br1c1&n=cli%3Bsvc%3Bcli%3Bentry%3Br1c2&n=ctx%3Bsvc%3Bctx%3B%3Br1c3&n=debughelpers%3Bsvc%3Bdebughelpers%3B%3Br2c0&n=globals%3Bsvc%3Bglobals%3B%3Br2c1&n=helpers%3Bsvc%3Bhelpers%3B%3Br2c2&n=sansio%3Bsvc%3Bsansio%3B%3Br0c0&n=sessions%3Bsvc%3Bsessions%3B%3Br2c3&n=signals%3Bbus%3Bsignals%3B%3Br3c0&n=templating%3Bfe%3Btemplating%3B%3Br3c1&n=testing%3Bsvc%3Btesting%3B%3Br3c2&n=typing%3Bsvc%3Btyping%3B%3Br3c3&n=wrappers%3Bsvc%3Bwrappers%3B%3Br4c0&n=tests%3Bsvc%3Btests%3B%3Br0c1&e=app%3Bctx&e=app%3Bdebughelpers&e=app%3Bglobals&e=app%3Bhelpers&e=app%3Bsessions&e=app%3Bsignals&e=app%3Btemplating&e=app%3Btesting&e=app%3Btyping&e=app%3Bwrappers&e=blueprints%3Bcli&e=blueprints%3Bglobals&e=blueprints%3Bhelpers&e=blueprints%3Btyping&e=blueprints%3Bwrappers&e=cli%3Bapp&e=cli%3Bglobals&e=cli%3Bhelpers&e=cli%3Btyping&e=ctx%3Bapp&e=ctx%3Bglobals&e=ctx%3Bhelpers&e=ctx%3Bsessions&e=ctx%3Bsignals&e=ctx%3Btyping&e=ctx%3Bwrappers&e=debughelpers%3Bblueprints&e=debughelpers%3Bglobals&e=debughelpers%3Btyping&e=debughelpers%3Bwrappers&e=globals%3Bapp&e=globals%3Bctx&e=globals%3Bsessions&e=globals%3Btyping&e=globals%3Bwrappers&e=helpers%3Bglobals&e=helpers%3Bsignals&e=helpers%3Btyping&e=helpers%3Bwrappers&e=sansio%3Bctx&b=src%3Bapp%20blueprints%20cli%20ctx%20debughelpers%20globals%20helpers%20sansio%20sessions%20signals%20templating%20testing%20typing%20wrappers)

**gin** (Go) — render=Frontend, internal tool packages in a boundary box:

![gin architecture](https://x-cmd.com/draw/arch2?title=gin&t=shadcn&n=binding%3Bsvc%3Bbinding%3B%3Br0c0&n=json%3Bsvc%3Bjson%3B%3Br2c2&n=gins%3Bsvc%3BginS%3B%3Br0c1&n=bytesconv%3Bsvc%3Bbytesconv%3B%3Br2c0&n=fs%3Bsvc%3Bfs%3B%3Br2c1&n=render%3Bfe%3Brender%3B%3Br1c0&e=binding%3Bbytesconv&e=binding%3Bjson&e=binding%3Brender&e=render%3Bbytesconv&e=render%3Bfs&e=render%3Bjson&b=internal%3Bbytesconv%20fs)

**express** (Node.js) — view=Frontend, lib core in a boundary box:

![express architecture](https://x-cmd.com/draw/arch2?title=express&t=shadcn&n=index%3Bsvc%3Bindex%3Bentry%3Br0c0&n=application%3Bsvc%3Bapplication%3B%3Br1c0&n=express%3Bsvc%3Bexpress%3B%3Br1c1&n=request%3Bsvc%3Brequest%3B%3Br2c0&n=response%3Bsvc%3Bresponse%3B%3Br2c1&n=utils%3Bsvc%3Butils%3B%3Br3c0&n=view%3Bfe%3Bview%3B%3Br2c2&n=test%3Bsvc%3Btest%3B%3Br0c1&e=application%3Bexpress&e=application%3Butils&e=application%3Bview&e=express%3Bapplication&e=express%3Brequest&e=express%3Bresponse&e=index%3Bexpress&e=response%3Butils&e=test%3Butils&e=test%3Bview&b=lib%3Bapplication%20express%20request%20response%20utils%20view)

## Local usage

```sh
make arch     # analyze -> build diagram -> sync README.md (+ README.zh.md)
make verify   # regenerate, then curl-check every embedded chart URL
make clean    # remove intermediate arch.json / diagram.md
```

Without `make`, use the exact same commands as CI:

```sh
python3 scripts/analyze_arch.py --root . --out arch.json
python3 scripts/build_diagram.py arch.json --out diagram.md
python3 scripts/update_readme.py --image-file diagram.md --readme README.md --readme README.zh.md
```

## Configuration

See the marked config block at the top of `scripts/build_diagram.py`:

| Variable | Default | Notes |
| --- | --- | --- |
| `ENDPOINT` | `https://x-cmd.com/draw/arch2` | rendering endpoint |
| `THEME` | `shadcn` | one of 21 themes (`xcmd`/`evil`/`pipeline`/`gradient`…) |
| `SCHEME` | `""` | set to `dark` to force the dark scheme |
| `BOUNDARIES` | `True` | draw top-level group boundaries (`--no-boundaries` to disable) |
| `IMG_ALT` | `Project Architecture` | image alt text |

`scripts/update_readme.py` config block: `MARK_START` / `MARK_END` markers
(must be alone on their line).

`analyze_arch.py` flags: `--max-nodes 15`, `--max-edges 40`,
`--max-depth 2` (tree fallback depth), `--title`.

## Architecture diagram of this repository (self-generated)

<!-- ARCH_DIAGRAM_START -->
![Project Architecture](https://x-cmd.com/draw/arch2?title=repo2draw&t=shadcn&n=scripts%3Bsvc%3Bscripts%3B%3Br0c0)
<!-- ARCH_DIAGRAM_END -->

## arch2 URL format reference

```
/draw/arch2?title=<title>&t=<theme>
    &n=<id>;<type>;<label>;<sub>;<grid>     grid = r<row>c<col>[w<w>][h<h>]
    &e=<from>;<to>[;<label>][;<variant>]    variant = main|dash (default plain)
    &b=<label>;<id>[ <id>...]               boundary box, ids space-separated (≥2 nodes)
Node types: ext fe be db cloud sec bus svc; encode ";" inside fields as %3B.
```

## Constraints and trade-offs

- Python 3 standard library only; CI runtime < 10s; zero third-party deps,
  zero AI / LLM calls.
- URL length guard: warn above 4000 chars, refuse to write above 7500
  (proxies and browsers truncate long GET URLs).
- When a package directory and its submodules are both candidates, the
  submodules are promoted and the parent collapses, keeping diagrams readable.
- Relative imports (`from . import x`) and third-party packages produce no
  edges, avoiding spider-web graphs.
