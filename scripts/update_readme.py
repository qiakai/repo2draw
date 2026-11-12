#!/usr/bin/env python3
"""Sync a diagram image line into README files between marker comments.

Input (one of):
  --image '![Alt](url)'   literal Markdown image line
  --image-file FILE       read the image line from FILE
  (default)               read the image line from stdin

Markers must be alone on their line:

    <!-- ARCH_DIAGRAM_START -->
    ...replaced...
    <!-- ARCH_DIAGRAM_END -->

When no marker block exists, one is appended at EOF. Files are written
atomically and their original permissions are preserved.

Usage:
  python3 scripts/build_diagram.py arch.json --out diagram.md
  python3 scripts/update_readme.py --image-file diagram.md \
      --readme README.md [--readme README.zh.md]
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

# ------------------------- 配置区（按需修改） -------------------------
MARK_START = "<!-- ARCH_DIAGRAM_START -->"
MARK_END = "<!-- ARCH_DIAGRAM_END -->"
# --------------------------------------------------------------------

PATTERN = re.compile(
    r"(?m)^" + re.escape(MARK_START) + r"[ \t]*\n(.*?)^"
    + re.escape(MARK_END) + r"[ \t]*$",
    re.DOTALL)


def sync_readme(readme_path, image_md):
    path = Path(readme_path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    if PATTERN.search(content):
        new_content = PATTERN.sub(
            lambda m: MARK_START + "\n" + image_md + "\n" + MARK_END, content)
        status = "updated"
    else:
        new_content = (content.rstrip("\n") + "\n\n" + MARK_START + "\n"
                       + image_md + "\n" + MARK_END + "\n")
        status = "appended"
    if new_content == content:
        return content, "unchanged"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent or Path(".")),
                               prefix=".readme-", suffix=".tmp")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(new_content)
    Path(tmp).replace(path)
    path.chmod(mode)
    return new_content, status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--readme", action="append", default=None,
                    help="README path (repeatable; default: README.md)")
    ap.add_argument("--image", default=None, help="literal Markdown image line")
    ap.add_argument("--image-file", default=None,
                    help="read Markdown image line from file")
    args = ap.parse_args()

    if args.image:
        image_md = args.image.strip()
    elif args.image_file:
        image_md = Path(args.image_file).read_text(encoding="utf-8").strip()
    else:
        image_md = sys.stdin.read().strip()
    if not image_md.startswith("!["):
        sys.exit("error: input does not look like a Markdown image line "
                 "(expected ![...](...))")

    for readme in (args.readme or ["README.md"]):
        _, status = sync_readme(readme, image_md)
        print(f"[repo2draw] {readme}: {status} "
              f"(markers: {MARK_START} ... {MARK_END})", file=sys.stderr)


if __name__ == "__main__":
    main()
