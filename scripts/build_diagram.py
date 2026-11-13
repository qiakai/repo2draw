#!/usr/bin/env python3
"""Build an x-cmd draw URL from arch.json (produced by analyze_arch.py).

Reads the architecture DSL produced by analyze_arch.py, encodes it into
arch2 URL parameters (nodes / edges / boundaries / theme), and outputs the
bare chart URL — nothing more. Recording the URL into a Markdown document
is a separate step (scripts/update_readme.py).

The arch2 endpoint format (verified against https://x-cmd.com/draw/arch2):

    /draw/arch2?title=<t>&t=<theme>
        &n=<id>;<type>;<label>;<sub>;<grid>     (grid = r<row>c<col>[w<w>][h<h>])
        &e=<from>;<to>[;<label>][;<variant>]    (variant = main|dash, default plain)
        &b=<label>;<id>[ <id>...]               (grouping boundary; ids space-joined)

Node types: ext fe be db cloud sec bus svc. Colors are fixed per node type
(Frontend/Backend/Database/Cloud/Security/Message bus/Service/External);
there is no per-node color override. Boundary boxes get their own accent
colors, so multi-node groups add extra palette variety. Invalid values
return HTTP 400 with the list of legal values.

Usage: python3 scripts/build_diagram.py arch.json [--out diagram.url]
"""
import argparse
import json
import sys
import urllib.parse
from collections import OrderedDict
from pathlib import Path

# ------------------------- 配置区（按需修改） -------------------------
ENDPOINT = "https://x-cmd.com/draw/arch2"
THEME = "shadcn"   # t= 主题（共 21 种：shadcn/xcmd/evil/pipeline/gradient...）
SCHEME = ""        # "dark" 强制暗色；"" 跟随系统
BOUNDARIES = True  # 是否按顶层目录绘制分组边界（≥2 节点才成组）
URL_WARN = 4000    # 超过则告警（浏览器/网关通常 2~8KB 截断）
URL_MAX = 7500     # 超过则拒绝输出
# --------------------------------------------------------------------

VALID_TYPES = {"ext", "fe", "be", "db", "cloud", "sec", "bus", "svc"}
VALID_VARIANTS = {"main", "dash"}


def enc(value):
    return urllib.parse.quote(str(value), safe="")


def node_param(node):
    ntype = node.get("type") if node.get("type") in VALID_TYPES else "svc"
    grid = node.get("grid") or {}
    cell = f"r{grid.get('row', 0)}c{grid.get('col', 0)}"
    if grid.get("w", 1) > 1:
        cell += f"w{grid['w']}"
    if grid.get("h", 1) > 1:
        cell += f"h{grid['h']}"
    fields = [node["id"], ntype, node.get("label") or node["id"],
              node.get("sub") or "", cell]
    return ";".join(fields)


def edge_param(edge):
    fields = [edge["from"], edge["to"]]
    if edge.get("label"):
        fields.append(edge["label"])
    if edge.get("variant") in VALID_VARIANTS:
        fields.append(edge["variant"])
    return ";".join(fields)


def boundary_params(model, enabled=True):
    if not enabled:
        return []
    groups = OrderedDict()
    for node in model.get("nodes", []):
        g = node.get("group") or ""
        if g:
            groups.setdefault(g, []).append(node["id"])
    return [f"{label};{' '.join(ids)}"
            for label, ids in groups.items() if len(ids) >= 2]


def build_url(model, theme=None, scheme=None, boundaries=BOUNDARIES):
    pairs = [("title", model.get("title") or model.get("repo") or "architecture"),
             ("t", theme or THEME)]
    for node in model.get("nodes", []):
        pairs.append(("n", node_param(node)))
    for edge in model.get("edges", []):
        pairs.append(("e", edge_param(edge)))
    for b in boundary_params(model, boundaries):
        pairs.append(("b", b))
    scheme = scheme if scheme is not None else SCHEME
    if scheme:
        pairs.append(("scheme", scheme))
    return ENDPOINT + "?" + "&".join(f"{k}={enc(v)}" for k, v in pairs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arch", nargs="?", default="arch.json",
                    help="arch DSL JSON path (default: arch.json)")
    ap.add_argument("--out", default=None,
                    help="write the bare URL to this file (default: stdout)")
    ap.add_argument("--theme", default=None, help="override theme")
    ap.add_argument("--title", default=None, help="override diagram title")
    ap.add_argument("--scheme", default=None, help="override color scheme")
    ap.add_argument("--no-boundaries", action="store_true",
                    help="skip boundary boxes")
    args = ap.parse_args()

    model = json.loads(Path(args.arch).read_text(encoding="utf-8"))
    if args.title:
        model["title"] = args.title
    url = build_url(model, theme=args.theme, scheme=args.scheme,
                    boundaries=not args.no_boundaries)

    if len(url) > URL_MAX:
        sys.exit(f"error: URL is {len(url)} chars (> {URL_MAX}); "
                 f"reduce --max-nodes or shorten labels")
    if len(url) > URL_WARN:
        print(f"warning: URL is {len(url)} chars (> {URL_WARN})", file=sys.stderr)
    print(f"[repo2draw] URL ({len(url)} chars)", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(url + "\n", encoding="utf-8")
        print(f"[repo2draw] wrote {args.out}", file=sys.stderr)
    else:
        print(url)


if __name__ == "__main__":
    main()
