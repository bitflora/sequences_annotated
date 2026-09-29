#!/usr/bin/env python3
"""Emit per-essay work items for analysis/essay-studies.jsonl.

The cited-study bars count only studies the essay itself cites: its footnotes,
plus studies named in the body by author and year. For every annotated essay
that has footnotes or an inline candidate, this writes one block listing them,
followed by the essay's skeptic-set notes, so a classifier can record which
notes assess which of the essay's studies (see build_findings.py for the row
format).

Usage:
    python3 scripts/essay_studies_batches.py OUT_DIR [ARTICLE ...]
"""
import html
import os
import re
import sys

from findings_common import (BOOKS, ROOT, SKEPTIC_SETS, annotated_articles, article_meta,
                             load_set, load_toc, strip_html)

# Markups: <p id='footnoteN'><span class='footnote'> and <a id='footnoteN'></a> <span class='footnote'>;
# a few Book VI pages drop the N, so those are numbered by position. Book VI's introduction
# instead writes <p>N. text <span class='back_to_citation_link'>.
FOOTNOTE = re.compile(r"id='footnote(\d*)'>(?:</a>)?\s*<span class='footnote'>(.*?)</span>", re.S)
NUMBERED = re.compile(r"<p>(\d+)\.\s*(.*?)<span class='back_to_citation_link'>", re.S)
# Sentences that may name a study: a plausible publication year, "et al.", or "study by".
INLINE = re.compile(r"\b(1[89]\d\d|20[01]\d)\b|et al\.|(?:study|studies|experiment|survey|paper) (?:by|of|from) [A-Z]")


def text(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def essay_parts(article):
    """(footnotes [(n, text)], inline candidate sentences) for an article page."""
    with open(os.path.join(ROOT, article + ".html"), encoding="utf-8") as f:
        page = f.read()
    i = page.find("<div class='footnotes")
    body, notes = (page[:i], page[i:]) if i >= 0 else (page, "")
    j = body.find("id='wikitext'")
    body = body[j:] if j >= 0 else body
    body = re.sub(r"<sup><a class='footnote'.*?</sup>", "", body, flags=re.S)
    body = re.sub(r"<(script|style)\b.*?</\1>", "", body, flags=re.S)
    footnotes = [(int(n) if n else k, text(t)) for k, (n, t) in enumerate(FOOTNOTE.findall(notes), 1)] \
        or [(int(n), text(t)) for n, t in NUMBERED.findall(notes)]
    sentences = re.split(r"(?<=[.!?”])\s+", text(body))
    inline = [s for s in sentences if INLINE.search(s) and len(s) < 600]
    return footnotes, inline


def block(article, sets, meta):
    footnotes, inline = essay_parts(article)
    if not footnotes and not inline:
        return None
    lines = [f"## ARTICLE {article} — \"{meta['title']}\" (Book {meta['book']}, seq {meta['sequence']})", ""]
    lines += [f"FOOTNOTE {n}: {t}" for n, t in footnotes]
    lines += [f"INLINE: {s}" for s in inline]
    lines.append("")
    for s in SKEPTIC_SETS:
        if s not in sets:
            continue
        for a in load_set(article, s) or []:
            lines.append(f"### {article}|{s}|{a['id']}")
            if a.get("quote"):
                lines.append(f"QUOTE: {a['quote']}")
            lines.append(f"NOTE: {strip_html(a['content'])}")
            lines.append("")
    return "\n".join(lines)


def main():
    out = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(out, exist_ok=True)
    toc = load_toc()
    arts = [(a, s) for a, s in annotated_articles() if not only or a in only]
    arts.sort(key=lambda x: (BOOKS.index(article_meta(x[0], toc)["book"]), article_meta(x[0], toc)["sequence"], x[0]))
    n = 0
    for art, sets in arts:
        b = block(art, sets, article_meta(art, toc))
        if b is None:
            continue
        n += 1
        with open(os.path.join(out, f"{n:03d}_{art}.md"), "w", encoding="utf-8") as f:
            f.write(b)
    print(f"{n} essays with footnotes or inline candidates (of {len(arts)})")


if __name__ == "__main__":
    main()
