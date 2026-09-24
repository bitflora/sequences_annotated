"""Shared helpers for the findings dashboard scripts.

Maps each article to its book and sequence (from Contents.html) and lists the
annotation sets the dashboard covers.
"""
import html
import json
import os
import re
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANN = os.path.join(ROOT, "annotations")

SKEPTIC_SETS = ["opus", "fable", "Opus5_5", "SkepticAstra"]
REBUTTAL_SETS = ["ropus", "RationalistAstra"]
SETS = SKEPTIC_SETS + REBUTTAL_SETS

BOOKS = ["I", "II", "III", "IV", "V", "VI"]


class _Toc(HTMLParser):
    """Walk Contents.html's nested lists, tagging each link with book/sequence."""

    def __init__(self):
        super().__init__()
        self.stack = []  # list kinds: 'alpha' for sequence lists, else 'plain'
        self.book = None
        self.seq_index = 0
        self.seq = None
        self.href = None
        self.text = ""
        self.pages = {}  # article -> dict

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("ol", "ul"):
            self.stack.append("alpha" if "upper-alpha" in (a.get("style") or "") else "plain")
            if tag == "ul" and self.book and len(self.stack) == 2:
                self.seq = None  # an unlettered list between sequences: intro/interlude
        elif tag == "a" and a.get("href", "").endswith(".html"):
            self.href = a["href"][:-5]
            self.text = ""

    def handle_endtag(self, tag):
        if tag in ("ol", "ul") and self.stack:
            self.stack.pop()
        elif tag == "a" and self.href:
            href, title = self.href, html.unescape(self.text).strip()
            self.href = None
            m = re.match(r"Book-([IV]+)-", href)
            if m:
                self.book, self.seq = m.group(1), None
                return
            if not self.book:
                return
            if self.stack and self.stack[-1] == "alpha":
                self.seq_index += 1
                self.seq = chr(ord("A") + self.seq_index - 1)
                self.seq_title = title
                return
            self.pages.setdefault(href, {
                "book": self.book,
                "sequence": self.seq or "interlude",
                "sequence_title": getattr(self, "seq_title", "") if self.seq else "Introduction / interlude",
                "title": title,
            })

    def handle_data(self, data):
        if self.href:
            self.text += data


def load_toc():
    p = _Toc()
    with open(os.path.join(ROOT, "Contents.html"), encoding="utf-8") as f:
        p.feed(f.read())
    return p.pages


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def article_meta(article, toc):
    """Look up an annotation article name in the TOC, tolerating hyphen/case variants."""
    if article in toc:
        return toc[article]
    n = _norm(article)
    for k, v in toc.items():
        if _norm(k) == n:
            return v
    return None


def strip_html(s):
    s = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"\2 [\1]", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def _logical_set(set_id, index_ids):
    """Books I-IV keep their only Opus pass as `OpusOld` (off by default for
    readers) but the dashboard still counts it as `opus`; Book VI's `OpusOld`
    is superseded by `Opus5_5` and stays out."""
    if set_id == "OpusOld" and "Opus5_5" not in index_ids:
        return "opus"
    return set_id


def load_set(article, set_id):
    p = os.path.join(ANN, f"{article}.{set_id}.json")
    if set_id == "opus" and not os.path.exists(p):
        p = os.path.join(ANN, f"{article}.OpusOld.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def annotated_articles():
    """(article, [set ids]) for every article with an index, restricted to SETS."""
    out = []
    for fn in sorted(os.listdir(ANN)):
        if not fn.endswith(".index.json"):
            continue
        art = fn[: -len(".index.json")]
        with open(os.path.join(ANN, fn), encoding="utf-8") as f:
            idx = json.load(f)
        ids = [e["id"] for e in idx]
        sets = [_logical_set(i, ids) for i in ids]
        sets = [s for s in sets if s in SETS]
        if sets:
            out.append((art, sets))
    return out
