#!/usr/bin/env python3
"""Emit classification work items for the findings dashboard.

Writes batch_NN.md files (plain-text notes grouped by article) into OUT_DIR.
Each rebuttal note is printed beneath the Fable note whose quote it shares, so
a classifier can judge its stance.

Usage:
    python3 scripts/findings_batches.py OUT_DIR [TARGET_NOTES_PER_BATCH]
"""
import os
import sys

from findings_common import BOOKS, REBUTTAL_SETS, SKEPTIC_SETS, annotated_articles, article_meta, load_set, load_toc, strip_html


def article_block(art, sets, meta):
    lines = [f"## ARTICLE {art} — \"{meta['title']}\" (Book {meta['book']}, seq {meta['sequence']})", ""]
    n = 0
    fable = {a["quote"]: a for a in (load_set(art, "fable") or []) if a.get("quote")}
    for s in SKEPTIC_SETS + REBUTTAL_SETS:
        if s not in sets:
            continue
        for a in load_set(art, s) or []:
            n += 1
            lines.append(f"### {art}|{s}|{a['id']}")
            if a.get("quote"):
                lines.append(f"QUOTE: {a['quote']}")
            if s in REBUTTAL_SETS and a.get("quote") in fable:
                lines.append(f"REPLYING TO FABLE #{fable[a['quote']]['id']}: {strip_html(fable[a['quote']]['content'])}")
            lines.append(f"NOTE: {strip_html(a['content'])}")
            lines.append("")
    return "\n".join(lines), n


def main():
    out = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    os.makedirs(out, exist_ok=True)
    toc = load_toc()
    arts = sorted(annotated_articles(), key=lambda x: (BOOKS.index(article_meta(x[0], toc)["book"]), article_meta(x[0], toc)["sequence"], x[0]))
    batches, cur, cur_n = [], [], 0
    for art, sets in arts:
        block, n = article_block(art, sets, article_meta(art, toc))
        cur.append(block)
        cur_n += n
        if cur_n >= target:
            batches.append((cur, cur_n))
            cur, cur_n = [], 0
    if cur:
        batches.append((cur, cur_n))
    for i, (blocks, n) in enumerate(batches, 1):
        with open(os.path.join(out, f"batch_{i:02d}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(blocks))
        print(f"batch_{i:02d}.md  {n} notes")


if __name__ == "__main__":
    main()
