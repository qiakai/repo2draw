#!/usr/bin/env python3
"""Record a chart URL into README files between marker comments.

Input (auto-detected; one of):
  --url URL          bare chart URL, wrapped into ![IMG_ALT](URL) here
  --url-file FILE    read a bare URL from FILE
  --image '![..](..)'  literal Markdown image line, used as-is
  (default)          read from stdin; URL or Markdown image line

Markers must be alone on their line:

    <!-- ARCH_DIAGRAM_START -->
    ...replaced...
    <!-- ARCH_DIAGRAM_END -->

When no marker block exists, one is appended at EOF. Files are written
atomically and their original permissions and CRLF line endings are
preserved.

Usage:
  python3 scripts/build_diagram.py arch.json --out diagram.url
  python3 scripts/update_readme.py --url-file diagram.url \
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
IMG_ALT = "Project Architecture"
# --------------------------------------------------------------------

PATTERN = re.compile(
    r"(?m)^" + re.escape(MARK_START) + r"[ \t]*\r?\n(.*?)^"
    + re.escape(MARK_END) + r"[ \t]*\r?$",
    re.DOTALL)


def sync_readme(readme_path, image_md):
    path = Path(readme_path)
    if path.exists():
        with open(path, "r", encoding="utf-8", newline="") as f:
            content = f.read()
    else:
        content = ""
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    nl = "\r\n" if "\r\n" in content else "\n"
    if PATTERN.search(content):
        new_content = PATTERN.sub(
            lambda m: MARK_START + nl + image_md + nl + MARK_END, content)
        status = "updated"
    else:
        new_content = (content.rstrip("\n") + nl + nl + MARK_START + nl
                       + image_md + nl + MARK_END + nl)
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


def to_image_md(text):
    text = text.strip()
    if text.startswith("!["):
        return text
    if text.startswith("http://") or text.startswith("https://"):
        return f"![{IMG_ALT}]({text})"
    sys.exit("error: input is neither a Markdown image line (![...](...)) "
             "nor an http(s) URL")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--readme", action="append", default=None,
                    help="README path (repeatable; default: README.md)")
    ap.add_argument("--url", default=None, help="bare chart URL")
    ap.add_argument("--url-file", default=None,
                    help="read a bare chart URL from file")
    ap.add_argument("--image", default=None, help="literal Markdown image line")
    args = ap.parse_args()

    if args.image:
        image_md = to_image_md(args.image)
    elif args.url:
        image_md = to_image_md(args.url)
    elif args.url_file:
        image_md = to_image_md(Path(args.url_file).read_text(encoding="utf-8"))
    else:
        image_md = to_image_md(sys.stdin.read())

    for readme in (args.readme or ["README.md"]):
        _, status = sync_readme(readme, image_md)
        print(f"[repo2draw] {readme}: {status} "
              f"(markers: {MARK_START} ... {MARK_END})", file=sys.stderr)


if __name__ == "__main__":
    main()
