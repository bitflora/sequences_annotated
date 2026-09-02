#!/usr/bin/env python3
"""Inject the annotations CSS/JS head tags into article HTML files.

Idempotent: skips files that already have the tags. Mirrors the two-line
addition documented in CLAUDE.md (annotations.css after skin.css; annotations.js
before </head>).

Usage:
    python3 scripts/add_annotation_tags.py File1.html File2.html ...
"""
import sys

CSS_LINE = "\t<link rel='stylesheet' href='wiki/pub/skins/readthesequences/annotations.css' type='text/css' />\n"
JS_LINE = '  <script src="wiki/pub/skins/readthesequences/annotations.js" defer></script>\n'
SKIN = "<link rel='stylesheet' href='wiki/pub/skins/readthesequences/skin.css' type='text/css' />"


def process(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if "annotations.css" in text or "annotations.js" in text:
        print(f"skip (already tagged): {path}")
        return
    lines = text.splitlines(keepends=True)
    out = []
    css_done = js_done = False
    for line in lines:
        if not css_done and SKIN in line:
            out.append(line)
            out.append(CSS_LINE)
            css_done = True
            continue
        if not js_done and "</head>" in line:
            out.append(JS_LINE)
            js_done = True
        out.append(line)
    if not (css_done and js_done):
        print(f"WARN anchor not found ({'css' if not css_done else ''} {'js' if not js_done else ''}): {path}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print(f"tagged: {path}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        process(p)
