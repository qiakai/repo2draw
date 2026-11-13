#!/usr/bin/env python3
"""Deterministic, zero-dependency architecture analyzer.

Detects the primary language from manifest files, extracts top-level
modules and their cross-module references with regexes only, and writes
a compact JSON DSL consumed by scripts/update_readme.py.

Usage: python3 scripts/analyze_arch.py --root . --out arch.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

LANG_EXTS = {
    "python": {".py"},
    "node": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
    "go": {".go"},
    "rust": {".rs"},
    "java": {".java", ".kt"},
    "csharp": {".cs"},
    "php": {".php"},
    "ruby": {".rb"},
    "swift": {".swift"},
    "c": {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh"},
}
ALL_EXTS = set().union(*LANG_EXTS.values())

BLACKLIST = {
    ".git", "node_modules", "dist", "build", "out", "target", "vendor",
    "venv", ".venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".next", ".nuxt", "coverage", ".idea", ".vscode",
    ".github", ".tox", ".eggs", "htmlcov", "site-packages", "docs",
    "third_party", ".terraform", "benchmarks", "testdata", "examples",
    "example", "demos", "samples",
}
CONTAINERS = {"src", "pkg", "packages", "apps", "internal", "cmd", "crate",
              "modules", "sources", "lib"}
ENTRY_NAMES = {"main", "cli", "app", "index", "server", "manage", "run"}
NOISE_FILES = {"__init__.py", "__main__.py", "conftest.py", "Package.swift"}
MAX_EXPAND_DEPTH = 8

TYPE_RULES = [
    ("db", {"db", "database", "models", "model", "storage", "store",
            "cache", "redis", "mongo", "sql", "schema", "migrations",
            "repository", "dao", "entity", "entities", "persist"}),
    ("sec", {"auth", "security", "crypto", "iam", "permission", "rbac",
             "login", "oauth", "jwt", "token", "tokens"}),
    ("fe", {"web", "frontend", "front", "ui", "pages", "templates",
            "templating", "static", "assets", "components", "public",
            "views", "view", "render", "rendering", "presenter"}),
    ("be", {"server", "backend", "api", "apis", "route", "routes",
            "router", "handler", "handlers", "controller", "controllers",
            "blueprint", "blueprints", "endpoints", "middleware",
            "gateway", "service", "services", "rpc", "grpc"}),
    ("bus", {"queue", "bus", "events", "event", "kafka", "mq", "worker",
             "workers", "jobs", "task", "tasks", "celery", "stream",
             "signal", "signals", "hooks", "hook", "pubsub", "notify",
             "notifications", "dispatcher"}),
    ("cloud", {"deploy", "deployment", "infra", "k8s", "kubernetes",
               "terraform", "helm", "docker", "charts", "ci", "cd",
               "monitoring", "metrics", "logging"}),
    ("ext", {"integration", "integrations", "sdk", "connector",
             "connectors", "external", "plugin", "plugins", "adapter",
             "adapters", "driver", "drivers", "compat", "client",
             "clients"}),
]
DEFAULT_TYPE = "svc"

PY_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)", re.M)
PY_FROM = re.compile(
    r"^\s*from\s+(\.*)([A-Za-z_][\w.]*)\s+import\s+([^\n(#]+)", re.M)
NODE_PATTERNS = [
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*(?:\(\s*)?['"]([^'"]+)['"]"""),
]
GO_BLOCK = re.compile(r"import\s*\(([^)]*)\)")
GO_SINGLE = re.compile(r'import\s+(?:[\w.]+\s+)?"([^"]+)"')
GO_MODULE = re.compile(r"^\s*module\s+(\S+)", re.M)
RUST_USE = re.compile(r"^\s*use\s+(?:crate|self|super)::([\w:]+)", re.M)
RUST_MOD = re.compile(r"^\s*(?:pub(?:\(crate\))?\s+)?mod\s+(\w+)\s*;", re.M)
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.M)
CS_USING = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)
PHP_USE = re.compile(r"^\s*use\s+([\w\\]+)", re.M)
PHP_REQ = re.compile(r"\brequire(?:_once)?\s*\(?\s*['\"]([^'\"]+)")
RUBY_REQ = re.compile(r"^\s*require\s+['\"]([^'\"]+)", re.M)
RUBY_REQREL = re.compile(r"^\s*require_relative\s+['\"]([^'\"]+)", re.M)
SWIFT_IMPORT = re.compile(r"^\s*import\s+(\w+)", re.M)
C_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)

MAX_CANDIDATES_SCAN = 80
MAX_FILES_SCANNED = 2000
VALID_TYPES = {"ext", "fe", "be", "db", "cloud", "sec", "bus", "svc"}
CONFIG_NAME = "repo2draw.json"


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:20] or "node"


def clean_label(name):
    label = re.sub(r"[;|]+", "/", name).strip()
    return label[:24] or name[:24]


def guess_type(name):
    n = name.lower()
    for t, kws in TYPE_RULES:
        if n in kws or any(k in n for k in kws if len(k) > 3):
            return t
    return DEFAULT_TYPE


def is_pruned(dirname):
    return dirname in BLACKLIST or dirname.startswith(".")


def detect_language(root):
    manifest = [("node", "package.json"), ("go", "go.mod"),
                ("rust", "Cargo.toml"), ("java", "pom.xml"),
                ("java", "build.gradle"), ("java", "build.gradle.kts"),
                ("php", "composer.json"), ("ruby", "Gemfile"),
                ("swift", "Package.swift"), ("c", "CMakeLists.txt"),
                ("c", "meson.build"),
                ("python", "pyproject.toml"),
                ("python", "requirements.txt"), ("python", "setup.py")]
    for lang, fname in manifest:
        if (root / fname).is_file():
            return lang
    if any(root.glob("*.csproj")) or any(root.glob("*.sln")):
        return "csharp"
    counts = {lang: 0 for lang in LANG_EXTS}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_pruned(d)]
        for f in filenames:
            ext = os.path.splitext(f)[1]
            for lang, exts in LANG_EXTS.items():
                if ext in exts:
                    counts[lang] += 1
    lang = max(counts, key=lambda k: counts[k])
    return lang if counts[lang] > 0 else None


def count_files(path, exts):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not is_pruned(d)]
        total += sum(1 for f in filenames
                     if exts is None or os.path.splitext(f)[1] in exts)
    return total


def source_files(root, lang):
    exts = LANG_EXTS.get(lang, ALL_EXTS)
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_pruned(d))
        for f in sorted(filenames):
            if os.path.splitext(f)[1] in exts:
                yield os.path.join(dirpath, f)
                n += 1
                if n >= MAX_FILES_SCANNED:
                    return


def discover_candidates(root, lang):
    exts = LANG_EXTS.get(lang, ALL_EXTS)
    cands = {}
    fcache = {}

    def cf(path):
        key = os.path.normpath(path)
        if key not in fcache:
            fcache[key] = count_files(key, exts)
        return fcache[key]

    def has_source_directly(path):
        try:
            return any(os.path.isfile(os.path.join(path, f))
                       and os.path.splitext(f)[1] in exts
                       for f in os.listdir(path))
        except OSError:
            return False

    def base_ok(fname):
        return fname not in NOISE_FILES

    def add(path):
        key = os.path.normpath(path)
        base = os.path.basename(key)
        name = os.path.splitext(base)[0]
        if key in cands or base in NOISE_FILES:
            return
        if os.path.isfile(key) and os.path.isdir(os.path.join(
                os.path.dirname(key), name)):
            return
        if os.path.isdir(key):
            for cand_key in list(cands):
                if os.path.splitext(cand_key)[0] == key:
                    del cands[cand_key]
        cands[key] = {
            "name": name,
            "path": key,
            "is_file": os.path.isfile(key),
            "files": 1 if os.path.isfile(key) else cf(key),
        }

    queue = []
    for entry in sorted(os.listdir(root)):
        p = os.path.join(str(root), entry)
        if os.path.isdir(p) and not is_pruned(entry):
            queue.append(p)
        elif (os.path.isfile(p) and os.path.splitext(entry)[1] in exts
              and base_ok(entry)):
            if lang == "go":
                continue  # root .go files belong to the module root node
            add(p)
    if lang == "go":
        add(str(root))

    depth = {p: 1 for p in queue}
    seen = set()
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        if not os.path.isdir(path):
            continue
        add(path)
        base = os.path.basename(path)
        is_pkg = lang == "python" and (Path(path) / "__init__.py").is_file()
        expand = (base in CONTAINERS or is_pkg or not has_source_directly(path)
                  or lang == "java")
        if not expand or depth[path] >= MAX_EXPAND_DEPTH:
            continue
        try:
            children = sorted(os.listdir(path))
        except OSError:
            continue
        for child in children:
            cp = os.path.join(path, child)
            if os.path.isdir(cp) and not is_pruned(child):
                if cf(cp) > 0 and cp not in depth:
                    depth[cp] = depth[path] + 1
                    queue.append(cp)
            elif (os.path.isfile(cp)
                  and os.path.splitext(child)[1] in exts
                  and base_ok(child)):
                add(cp)

    for c in sorted(cands.values(), key=lambda c: c["path"]):
        cid = slug(c["name"])
        n = 2
        while any(c2.get("id") == cid for c2 in cands.values()
                  if c2 is not c):
            cid = f"{slug(c['name'])}-{n}"
            n += 1
        c["id"] = cid
    return {c["id"]: c for c in cands.values()}


def owner_of(filepath, cands):
    best = None
    for c in cands.values():
        p = c["path"]
        if filepath == p or filepath.startswith(p + os.sep):
            if best is None or len(p) > len(best["path"]):
                best = c
    return best


def is_ancestor(a, b):
    return b["path"].startswith(a["path"] + os.sep)


def resolve_dotted(spec, by_name, module_prefixes):
    parts = [p for p in re.split(r"[./:\\]+", spec) if p and p != "mod"]
    for pre in module_prefixes:
        if parts and parts[0] == pre:
            parts = parts[1:]
            break
    targets, seen = [], set()
    for p in parts:
        c = by_name.get(p)
        if c and c["id"] not in seen:
            seen.add(c["id"])
            targets.append(c)
    return targets


def resolve_relative(filepath, spec, by_path, root, exts):
    base = os.path.dirname(filepath)
    p = os.path.normpath(os.path.join(base, spec))
    p = os.path.splitext(p)[0]
    cur = p
    while len(cur) >= len(root):
        if cur in by_path:
            return by_path[cur]
        for ext in exts:
            if cur + ext in by_path:
                return by_path[cur + ext]
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def resolve_py_relative(filepath, dots, base, names, by_path, exts):
    d = os.path.dirname(filepath)
    for _ in range(max(dots - 1, 0)):
        d = os.path.dirname(d)
    roots = [os.path.join(d, base)] if base else [d]
    for r in roots:
        yield_paths = [r]
        for nm in names.split(","):
            nm = nm.strip().split(" as ")[0].strip()
            if nm and nm != "*":
                yield_paths.append(os.path.join(r, nm))
        for p in yield_paths:
            if p in by_path:
                yield by_path[p]
                continue
            for ext in exts:
                if p + ext in by_path:
                    yield by_path[p + ext]
                    break


def filter_targets(owner, targets):
    if owner is None:
        return []
    out = []
    for t in targets:
        if t["id"] == owner["id"] or is_ancestor(t, owner):
            continue
        if any(is_ancestor(t, o) for o in targets if o["id"] != t["id"]):
            continue
        out.append(t)
    return out


def parse_names(names):
    out = []
    for nm in names.split(","):
        nm = nm.strip().split(" as ")[0].strip()
        if nm and nm != "*":
            out.append(nm)
    return out


def extract_edges(root, lang, cands):
    by_name = {}
    by_path = {}
    for c in cands.values():
        by_name.setdefault(c["name"], c)
        by_path[c["path"]] = c
    exts = LANG_EXTS.get(lang, ALL_EXTS)
    module_prefixes = set()
    go_mod = None
    root_cand = by_path.get(os.path.normpath(str(root)))
    if lang == "go":
        gomod = root / "go.mod"
        if gomod.is_file():
            m = GO_MODULE.search(gomod.read_text(errors="ignore"))
            if m:
                go_mod = m.group(1).strip().strip('"')
                module_prefixes.add(go_mod)
                module_prefixes.add(go_mod.split("/")[-1])
    edges = set()
    for filepath in source_files(root, lang):
        owner = owner_of(filepath, cands)
        if owner is None:
            continue
        text = Path(filepath).read_text(errors="ignore")
        specs = []
        rel_specs = []
        if lang == "python":
            specs += PY_IMPORT.findall(text)
            for dots, base, names in PY_FROM.findall(text):
                if dots:
                    rel_specs.append(("py", dots, base, names))
                else:
                    specs.append(base)
                    for nm in parse_names(names):
                        specs.append(f"{base}.{nm}")
        elif lang == "node":
            for pat in NODE_PATTERNS:
                for s in pat.findall(text):
                    (rel_specs if s.startswith(".") else specs).append(s)
        elif lang == "go":
            for block in GO_BLOCK.findall(text):
                specs += re.findall(r'"([^"]+)"', block)
            specs += GO_SINGLE.findall(text)
        elif lang == "rust":
            specs += [s.replace("::", ".") for s in RUST_USE.findall(text)]
            specs += RUST_MOD.findall(text)
        elif lang == "java":
            specs += JAVA_IMPORT.findall(text)
        elif lang == "csharp":
            specs += CS_USING.findall(text)
        elif lang == "php":
            for s in PHP_USE.findall(text):
                specs.append(s.replace("\\", "."))
            for s in PHP_REQ.findall(text):
                (rel_specs if s.startswith(".") else specs).append(s)
        elif lang == "ruby":
            for s in RUBY_REQ.findall(text):
                specs.append(s)
            for s in RUBY_REQREL.findall(text):
                rel_specs.append(s)
        elif lang == "swift":
            specs += SWIFT_IMPORT.findall(text)
        elif lang == "c":
            for s in C_INCLUDE.findall(text):
                rel_specs.append(s)
        for spec in specs:
            spec = spec.strip().strip("'\"")
            if not spec:
                continue
            if lang == "go" and go_mod and spec in (go_mod, go_mod.split("/")[-1]):
                targets = [root_cand] if root_cand else []
            elif lang == "node" and (spec.startswith("@/")
                                     or spec.startswith("~/")):
                targets = resolve_dotted(spec[2:], by_name, module_prefixes)
            else:
                targets = resolve_dotted(spec, by_name, module_prefixes)
            for t in filter_targets(owner, targets):
                edges.add((owner["id"], t["id"]))
        for item in rel_specs:
            if isinstance(item, tuple):
                _, dots, base, names = item
                targets = list(resolve_py_relative(filepath, len(dots), base,
                                                   names, by_path, exts))
            else:
                t = resolve_relative(filepath, item, by_path, str(root), exts)
                targets = [t] if t else []
            for t in filter_targets(owner, targets):
                edges.add((owner["id"], t["id"]))
    return edges


def tree_fallback(root, max_nodes, max_depth):
    nodes, edges = [], []
    queue = [(str(root), None, 0)]
    used_ids = set()

    def fresh_id(name):
        cid = slug(name)
        n = 2
        while cid in used_ids:
            cid = f"{slug(name)}-{n}"
            n += 1
        used_ids.add(cid)
        return cid

    while queue and len(nodes) < max_nodes:
        path, parent, depth = queue.pop(0)
        name = os.path.basename(path) or os.path.basename(str(root))
        cid = fresh_id(name)
        nodes.append({"id": cid, "type": guess_type(name),
                      "label": clean_label(name),
                      "sub": "entry" if parent is None else "",
                      "group": group_of(path, root)})
        if parent is not None:
            edges.append((parent, cid))
        if depth < max_depth:
            try:
                children = sorted(
                    os.path.join(path, d) for d in os.listdir(path)
                    if os.path.isdir(os.path.join(path, d))
                    and not is_pruned(d)
                    and count_files(os.path.join(path, d), None) > 0)
            except OSError:
                children = []
            queue += [(c, cid, depth + 1) for c in children]
    return nodes, edges


def group_of(path, root):
    rel = os.path.relpath(path, str(root))
    parts = rel.split(os.sep)
    if len(parts) <= 1:
        return ""
    return re.sub(r"[;|]+", "/", parts[0])[:24]


def layout_grid(nodes, edges):
    if not edges:
        for i, nd in enumerate(nodes):
            nd["grid"] = {"row": i // 4, "col": i % 4}
        return
    ids = [nd["id"] for nd in nodes]
    adj = {i: [] for i in ids}
    for a, b in edges:
        adj[a].append(b)

    sys.setrecursionlimit(max(1000, len(ids) * 4 + 100))
    index, lowlink, on_stack, comp = {}, {}, set(), {}
    stack, counter, ncomp = [], [0], [0]

    def strongconnect(v):
        index[v] = lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj[v]:
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp[w] = ncomp[0]
                if w == v:
                    break
            ncomp[0] += 1

    for v in ids:
        if v not in index:
            strongconnect(v)

    cadj = {i: set() for i in range(ncomp[0])}
    indeg = {i: 0 for i in range(ncomp[0])}
    for a, b in edges:
        ca, cb = comp[a], comp[b]
        if ca != cb and cb not in cadj[ca]:
            cadj[ca].add(cb)
            indeg[cb] += 1
    layer = {i: 0 for i in range(ncomp[0])}
    queue = [i for i in range(ncomp[0]) if indeg[i] == 0]
    head = 0
    while head < len(queue):
        c = queue[head]
        head += 1
        for d in cadj[c]:
            if layer[d] < layer[c] + 1:
                layer[d] = layer[c] + 1
            indeg[d] -= 1
            if indeg[d] == 0:
                queue.append(d)

    placed = set()
    for nd in sorted(nodes, key=lambda n: (layer[comp[n["id"]]], n["id"])):
        row, col = layer[comp[nd["id"]]], 0
        while True:
            if col >= 4:
                row, col = row + 1, 0
            if (row, col) not in placed:
                break
            col += 1
        placed.add((row, col))
        nd["grid"] = {"row": row, "col": col}


def model_from_config(cfg, root, max_nodes, max_edges, title):
    raw_nodes = cfg.get("nodes") or []
    nodes, explicit, seen = [], {}, set()
    for nd in raw_nodes:
        nid = slug(str(nd.get("id") or nd.get("label") or "node"))
        if not nid or nid in seen:
            continue
        seen.add(nid)
        grid = nd.get("grid")
        if isinstance(grid, dict):
            try:
                explicit[nid] = {"row": max(int(grid["row"]), 0),
                                 "col": max(int(grid["col"]), 0)}
            except (KeyError, TypeError, ValueError):
                pass
        nodes.append({
            "id": nid,
            "type": nd.get("type") if nd.get("type") in VALID_TYPES else "svc",
            "label": clean_label(str(nd.get("label") or nid)),
            "sub": re.sub(r"[;|]+", "/", str(nd.get("sub") or ""))[:24],
            "group": re.sub(r"[;|]+", "/", str(nd.get("group") or ""))[:24],
        })
    if len(nodes) > max_nodes:
        print(f"[repo2draw] warning: {len(nodes)} config nodes, keeping {max_nodes}",
              file=sys.stderr)
        nodes = nodes[:max_nodes]
        explicit = {k: v for k, v in explicit.items()
                    if k in {n["id"] for n in nodes}}
    keep = {n["id"] for n in nodes}
    edges, seen_e = [], set()
    for e in (cfg.get("edges") or []):
        a = slug(str(e.get("from", "")))
        b = slug(str(e.get("to", "")))
        if a not in keep or b not in keep or a == b or (a, b) in seen_e:
            continue
        seen_e.add((a, b))
        edge = {"from": a, "to": b}
        if e.get("label"):
            edge["label"] = re.sub(r"[;]+", "/", str(e["label"]))[:24]
        if e.get("variant") in ("main", "dash"):
            edge["variant"] = e["variant"]
        edges.append(edge)
    edges = edges[:max_edges]
    if not nodes:
        sys.exit("error: repo2draw.json declares no usable nodes")
    layout_grid(nodes, [(e["from"], e["to"]) for e in edges])
    for nd in nodes:
        if nd["id"] in explicit:
            nd["grid"] = explicit[nd["id"]]
    return {
        "generator": "repo2draw",
        "version": 1,
        "repo": os.path.basename(str(root)) or "repo",
        "language": "config",
        "title": title or cfg.get("title") or os.path.basename(str(root)) or "repo",
        "nodes": [{k: nd[k] for k in ("id", "type", "label", "sub", "group", "grid")}
                  for nd in nodes],
        "edges": edges,
    }


def build_model(root, max_nodes, max_edges, max_depth, title, config=None):
    cfg_path = Path(config) if config else (root / CONFIG_NAME)
    if cfg_path.is_file():
        print(f"[repo2draw] using declared architecture: {cfg_path}", file=sys.stderr)
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"error: {cfg_path}: invalid JSON: {e}")
        return model_from_config(cfg, root, max_nodes, max_edges, title)
    lang = detect_language(root)
    if lang is None:
        nodes, edge_tuples = tree_fallback(root, max_nodes, max_depth)
        language = "tree"
    else:
        full = discover_candidates(root, lang)
        dropped = set()
        for cid, c in full.items():
            if c["is_file"]:
                continue
            if any(o["path"].startswith(c["path"] + os.sep)
                   for o in full.values() if o is not c):
                dropped.add(cid)
        pool = {cid: c for cid, c in full.items() if cid not in dropped}
        ranked = sorted(pool.values(),
                        key=lambda c: (-c["files"], c["path"]))[:MAX_CANDIDATES_SCAN]
        raw_edges = extract_edges(root, lang, full)
        score = {c["id"]: c["files"] + 2 * sum(1 for e in raw_edges
                                              if c["id"] in e)
                 for c in ranked}
        keep = sorted(ranked, key=lambda c: (-score[c["id"]], c["path"]))
        keep = keep[:max_nodes]
        keep_ids = {c["id"] for c in keep}
        edge_tuples = sorted({e for e in raw_edges
                              if e[0] in keep_ids and e[1] in keep_ids})[:max_edges]
        nodes = [{"id": c["id"], "type": guess_type(c["name"]),
                  "label": clean_label(c["name"]),
                  "sub": "entry" if c["name"] in ENTRY_NAMES else "",
                  "group": group_of(c["path"], root)}
                 for c in sorted(keep, key=lambda c: c["path"])]
        language = lang
    if not nodes:
        name = os.path.basename(str(root)) or "repo"
        nodes = [{"id": slug(name), "type": "svc",
                  "label": clean_label(name), "sub": "", "group": ""}]
        edge_tuples = []
    layout_grid(nodes, edge_tuples)
    if language == "tree":
        edges = [{"from": a, "to": b, "variant": "dash"} for a, b in edge_tuples]
    else:
        edges = [{"from": a, "to": b} for a, b in edge_tuples]
    return {
        "generator": "repo2draw",
        "version": 1,
        "repo": os.path.basename(str(root)) or "repo",
        "language": language,
        "title": title or os.path.basename(str(root)) or "repo",
        "nodes": [{k: nd[k] for k in ("id", "type", "label", "sub", "group", "grid")}
                  for nd in nodes],
        "edges": edges,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("--out", default="arch.json",
                    help="output JSON path, '-' for stdout (default: arch.json)")
    ap.add_argument("--max-nodes", type=int, default=15)
    ap.add_argument("--max-edges", type=int, default=40)
    ap.add_argument("--max-depth", type=int, default=2,
                    help="directory-tree fallback depth")
    ap.add_argument("--title", default=None, help="diagram title")
    ap.add_argument("--config", default=None,
                    help=f"declared architecture JSON (default: ./{CONFIG_NAME} when present)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"error: {root} is not a directory")

    model = build_model(root, args.max_nodes, args.max_edges,
                        args.max_depth, args.title, config=args.config)
    payload = json.dumps(model, ensure_ascii=False, indent=2)

    print(f"[repo2draw] language={model['language']} "
          f"nodes={len(model['nodes'])} edges={len(model['edges'])} "
          f"root={root}", file=sys.stderr)

    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(f"[repo2draw] wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
