#!/usr/bin/env python3
"""Validate analysis/findings.jsonl and aggregate it for Findings.html.

findings.jsonl holds one LLM-assigned classification per annotation in the
current sets (see findings_common.SETS). This script checks every row against
the annotation files, attaches book/sequence from Contents.html, pairs each
rebuttal note with the Fable note whose quote it shares, and writes
analysis/findings-summary.json.

The cited-study charts count only studies the essays themselves cite, listed in
analysis/essay-studies.jsonl: one row per (article, study) with the footnote
number (null for a study named in the body) and the skeptic notes that assess
that study, each with a verdict on it. A row with no assessments is a study the
essay cites that no note judges; it is shown as "not assessed".
scripts/essay_studies_batches.py prints each essay's references beside its
notes for filling that file in.

Usage:
    python3 scripts/build_findings.py [FRAGMENT.jsonl ...]

With fragment paths, they are merged (in order) into analysis/findings.jsonl
first; without, the existing findings.jsonl is used.
"""
import collections
import datetime
import glob
import html
import json
import math
import os
import re
import sys

from findings_common import (BOOKS, REBUTTAL_SETS, ROOT, SETS, SKEPTIC_SETS,
                             annotated_articles, article_meta, load_set, load_toc)

FINDINGS = os.path.join(ROOT, "analysis", "findings.jsonl")
SUMMARY = os.path.join(ROOT, "analysis", "findings-summary.json")
INDEX = os.path.join(ROOT, "index.html")
TOC_PAGES = os.path.join(ROOT, "*.html")
ARTICLE_BARS = os.path.join(ROOT, "analysis", "article-studies.json")
ESSAY_STUDIES = os.path.join(ROOT, "analysis", "essay-studies.jsonl")

TARGETS = ["cited_study", "empirical_claim", "historical_fact", "attribution",
           "ai_prediction", "argument", "prior_work", "other"]
# Ordered from best to worst for the essay.
VERDICTS = ["holds", "holds_qualified", "contested", "unfalsifiable_or_na",
            "weakened", "failed_replication", "retracted_or_fraud", "false_or_misattributed"]
GROUP = {"holds": "stands", "holds_qualified": "stands",
         "contested": "open", "unfalsifiable_or_na": "open",
         "weakened": "damaged", "failed_replication": "damaged",
         "retracted_or_fraud": "damaged", "false_or_misattributed": "damaged"}
# An essay-cited study that no note assesses.
STUDY_VERDICTS = VERDICTS + ["unassessed"]
STUDY_GROUP = dict(GROUP, unassessed="unassessed")
BAR_GROUPS = ("stands", "open", "damaged", "unassessed")
SHORT_VERDICT = {"holds": "holds", "holds_qualified": "holds, qualified", "contested": "contested",
                 "unfalsifiable_or_na": "no empirical verdict", "weakened": "weakened",
                 "failed_replication": "failed replication", "retracted_or_fraud": "retracted",
                 "false_or_misattributed": "misreported", "unassessed": "not assessed"}
# Study names the classifier wrote more than one way.
SOURCE_ALIASES = {
    "Gilbert et al. 1993": "Gilbert, Tafarodi & Malone 1993",
    "Darley & Latane 1968": "Latané & Darley 1968",
}
STANCES = ["concedes", "partly_concedes", "contests"]
MODES = ["essay_text", "other_study", "turns_source", "technical", "reread", "concession_only"]


def die(msg):
    sys.exit(f"build_findings: {msg}")


def merge(fragments):
    rows = []
    for p in fragments:
        with open(p, encoding="utf-8") as f:
            rows += [line for line in f if line.strip()]
    os.makedirs(os.path.dirname(FINDINGS), exist_ok=True)
    with open(FINDINGS, "w", encoding="utf-8") as f:
        f.writelines(r if r.endswith("\n") else r + "\n" for r in rows)


def expected_notes(toc):
    """key -> (article, set, annotation dict, meta) for every note in scope."""
    out = {}
    for art, sets in annotated_articles():
        meta = article_meta(art, toc)
        for s in sets:
            for a in load_set(art, s) or []:
                out[f"{art}|{s}|{a['id']}"] = (art, s, a, meta)
    return out


def load_rows(expected):
    rows, errors = {}, []
    with open(FINDINGS, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {n}: bad JSON ({e})")
                continue
            k = r.get("key")
            if k not in expected:
                errors.append(f"line {n}: unknown key {k!r}")
                continue
            if k in rows:
                errors.append(f"line {n}: duplicate key {k}")
            s = k.split("|")[1]
            if r.get("target") not in TARGETS:
                errors.append(f"{k}: bad target {r.get('target')!r}")
            if r.get("verdict") not in VERDICTS:
                errors.append(f"{k}: bad verdict {r.get('verdict')!r}")
            if s in REBUTTAL_SETS:
                if r.get("stance") not in STANCES:
                    errors.append(f"{k}: bad stance {r.get('stance')!r}")
                if r.get("mode") not in MODES:
                    errors.append(f"{k}: bad mode {r.get('mode')!r}")
            rows[k] = r
    missing = sorted(set(expected) - set(rows))
    if missing:
        errors.append(f"{len(missing)} notes unclassified, e.g. {missing[:5]}")
    if errors:
        die("\n  " + "\n  ".join(errors[:40]) + (f"\n  ... {len(errors) - 40} more" if len(errors) > 40 else ""))
    return rows


def load_essay_studies(note_by_key):
    """Rows of analysis/essay-studies.jsonl, validated against the in-scope skeptic notes."""
    rows, seen, errors = [], set(), []
    with open(ESSAY_STUDIES, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"essay-studies line {n}: bad JSON ({e})")
                continue
            study = " ".join((r.get("study") or "").replace("&amp;", "&").split())
            r["study"] = SOURCE_ALIASES.get(study, study)
            art = r.get("article")
            if not study or not any(note["article"] == art for note in note_by_key.values()):
                errors.append(f"essay-studies line {n}: unknown article {art!r} or empty study")
                continue
            if (art, r["study"]) in seen:
                errors.append(f"essay-studies line {n}: duplicate {art} / {r['study']}")
            seen.add((art, r["study"]))
            if r.get("footnote") is not None and not isinstance(r["footnote"], int):
                errors.append(f"essay-studies line {n}: footnote must be an integer or null")
            for a in r.get("assessments") or []:
                note = note_by_key.get(a.get("note"))
                if not note or note["set"] not in SKEPTIC_SETS or note["article"] != art:
                    errors.append(f"essay-studies line {n}: {a.get('note')!r} is not an in-scope skeptic note on {art}")
                if a.get("verdict") not in VERDICTS:
                    errors.append(f"essay-studies line {n}: bad verdict {a.get('verdict')!r}")
            r["assessments"] = r.get("assessments") or []
            rows.append(r)
    if errors:
        die("\n  " + "\n  ".join(errors[:40]))
    return rows


def set_codes(article):
    """set id -> the short code annotations.js prefixes marker numbers with."""
    with open(os.path.join(ROOT, "annotations", f"{article}.index.json"), encoding="utf-8") as f:
        return {e["id"]: e.get("code") or e["id"][0].upper() for e in json.load(f)}


def counter_dict(c, keys):
    return {k: c.get(k, 0) for k in keys}


def study_label(c):
    """("N of M cited studies hold up", ["K damaged", ...]) for a Counter of study groups."""
    total = sum(c.values())
    noun = "study holds" if total == 1 else "studies hold"
    extra = [f"{c['damaged']} damaged"] if c["damaged"] else []
    extra += [f"{c['open']} contested"] if c["open"] else []
    extra += [f"{c['unassessed']} not assessed"] if c["unassessed"] else []
    return f"{c['stands']} of {total} cited {noun} up", extra


def bar_inner(c):
    """The bar and caption spans shared by the front page and the article titles."""
    segs = "".join(f'<span style="flex:{c[g]};background:var(--st-{g})"></span>' for g in BAR_GROUPS if c[g])
    label, extra = study_label(c)
    aria = label + (", " + ", ".join(extra) if extra else "")
    return (f'<span class="bar" role="img" aria-label="{aria}">{segs}</span><span class="cap">{label}</span>'
            + (f'<span class="cap">{" · ".join(extra)}</span>' if extra else ""))


def bar_html(c, cls, title):
    """A stands/open/damaged bar with its caption, as on the front page; empty when no studies are cited."""
    if not sum(c.values()):
        return ""
    return f'<a class="{cls}" href="Findings.html" title="{title}">{bar_inner(c)}</a>'


def article_bar_html(article, cites, study_by_name, note_by_key):
    """The article-title bar plus a list of the essay's cited studies, each linked to its footnote
    and to the notes on this page that assess it."""
    c = collections.Counter(study_by_name[r["study"]]["group"] for r in cites)
    codes = set_codes(article)
    with open(os.path.join(ROOT, article + ".html"), encoding="utf-8") as f:
        page = f.read()
    order = {g: i for i, g in enumerate(BAR_GROUPS)}
    items = []
    for r in sorted(cites, key=lambda r: (order[study_by_name[r["study"]]["group"]], r["footnote"] or 999, r["study"])):
        st = study_by_name[r["study"]]
        name = html.escape(r["study"])
        if r["footnote"] and f"id='footnote{r['footnote']}'" in page:
            name = f'<a href="#footnote{r["footnote"]}">{name}</a>'
        refs = []
        for a in r["assessments"]:
            note = note_by_key[a["note"]]
            refs.append(f'<a class="study-note" href="#annotation-{note["set"]}-{note["id"]}" data-set="{note["set"]}" '
                        f'title="{html.escape(SHORT_VERDICT[a["verdict"]])}">{codes.get(note["set"], "")}{note["id"]}</a>')
        where = ""
        if not refs and st["group"] != "unassessed":
            other = next(n for n in st["notes"] if n["article"] != article)
            where = f' <a class="study-elsewhere" href="{other["article"]}.html">see {html.escape(other["title"])}</a>'
        items.append(f'<span class="study"><i class="dot {st["group"]}"></i>{name} '
                     f'<span class="verdict">{SHORT_VERDICT[st["verdict"]]}</span>'
                     + (f' <span class="refs">{" ".join(refs)}</span>' if refs else "") + where + '</span>')
    body = "".join(items)
    n = len(cites)
    listing = (f'<span class="study-list">{body}</span>' if n <= 4 else
               f'<details class="study-list"><summary>The {n} studies</summary>{body}</details>')
    return (f'<span class="article-studies"><a class="studies-bar" href="Findings.html" '
            f'title="Cited studies in this essay">{bar_inner(c)}</a>{listing}</span>')


def write_index_bars(study_fate):
    """Rewrite the per-book cited-study bars between the <!-- studies:B --> markers in index.html."""
    with open(INDEX, encoding="utf-8") as f:
        page = f.read()
    for b in BOOKS:
        c = collections.Counter()
        for v, n in study_fate[b].items():
            c[STUDY_GROUP[v]] += n
        html = bar_html(c, "book-studies", f"Cited studies in Book {b}")
        start, end = f"<!-- studies:{b} -->", f"<!-- /studies:{b} -->"
        i, j = page.find(start), page.find(end)
        if i < 0 or j < i:
            die(f"index.html has no {start} ... {end} markers")
        page = page[:i + len(start)] + html + page[j:]
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(page)


def pie_svg(c, size):
    """A small inline SVG pie of stands/open/damaged/unassessed study counts."""
    total = sum(c.values())
    r = size / 2
    parts, a = [], -math.pi / 2
    for g in BAR_GROUPS:
        if not c[g]:
            continue
        if c[g] == total:
            parts.append(f'<circle class="{g}" cx="{r}" cy="{r}" r="{r}"/>')
            break
        b = a + 2 * math.pi * c[g] / total
        x0, y0 = r + r * math.cos(a), r + r * math.sin(a)
        x1, y1 = r + r * math.cos(b), r + r * math.sin(b)
        large = 1 if b - a > math.pi else 0
        parts.append(f'<path class="{g}" d="M{r},{r}L{x0:.2f},{y0:.2f}A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f}Z"/>')
        a = b
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" aria-hidden="true">'
            + "".join(parts) + "</svg>")


def pie_html(groups, size, cls):
    """Pie plus tooltip for a {source: group} map; empty when no studies are cited."""
    if not groups:
        return ""
    label, extra = study_label(collections.Counter(groups.values()))
    label += "; " + ", ".join(extra) if extra else ""
    c = collections.Counter(groups.values())
    return (f'<!--pie--><a class="study-pie {cls}" href="Findings.html" title="{label}" '
            f'role="img" aria-label="{label}">{pie_svg(c, size)}</a><!--/pie-->')


def _toc_region(page):
    """(start, end) of a page's table of contents: the Book/sequence .toc div or Contents.html's big_toc."""
    for start in ("<div class='toc' >", "<div class='big_toc' >"):
        i = page.find(start)
        if i >= 0:
            j = page.find("<div class='bottom_nav", i)
            return (i, j) if j >= 0 else None
    return None


def write_toc_pies(studies, cites, note_by_key):
    """Put a cited-study pie after every chapter, sequence and book link in the tables of contents
    (Book pages, sequence pages, Contents.html) and in each sequence page's heading, and write
    analysis/article-studies.json for annotations.js to put a bar under each article's title."""
    norm = lambda a: re.sub(r"[^a-z0-9]", "", a.lower())
    study_by_name = {st["source"]: st for st in studies}
    groups = collections.defaultdict(dict)  # normalized page name -> {source: group}
    for r in cites:
        groups[norm(r["article"])][r["study"]] = study_by_name[r["study"]]["group"]
    item = re.compile(r"<li[^>]*>\s*<a class='wikilink' href='([^']+)\.html'>")
    pages = {}
    for path in sorted(glob.glob(TOC_PAGES)):
        with open(path, encoding="utf-8") as f:
            page = re.sub(r"<!--pie-->.*?<!--/pie-->", "", f.read(), flags=re.S)
        region = _toc_region(page)
        if region:
            pages[path] = (page, region)
    # Sequence and Book pages pool the studies of the chapters they list.
    for path, (page, (i, j)) in pages.items():
        name = os.path.basename(path)[:-5]
        if name != "Contents":
            for a in item.findall(page[i:j]):
                groups[norm(name)].update(groups.get(norm(a), {}))

    link = re.compile(r"(<a class='wikilink' href='([^']+)\.html'>.*?</a>)", re.S)
    for path, (page, (i, j)) in pages.items():
        toc = page[i:j]
        # Links inside a heading (the Book pages' sequence titles) get the larger pie.
        heads = [(m.start(), m.end()) for m in re.finditer(r"<h3>.*?</h3>", toc, re.S)]
        toc = link.sub(lambda m: m.group(1) + pie_html(
            groups.get(norm(m.group(2)), {}), *((16, "sequence") if any(a <= m.start() < b for a, b in heads)
                                                else (11, "chapter"))), toc)
        # A sequence page's own heading has no link; give it the page's pooled pie.
        toc = re.sub(r"(<h3>(?:(?!<a ).)*?)(</h3>)",
                     lambda m: m.group(1) + pie_html(groups.get(norm(os.path.basename(path)[:-5]), {}), 16, "sequence")
                     + m.group(2), toc, flags=re.S)
        page = page[:i] + toc + page[j:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)

    by_article = collections.defaultdict(list)
    for r in cites:
        by_article[r["article"]].append(r)
    with open(ARTICLE_BARS, "w", encoding="utf-8") as f:
        json.dump({a: article_bar_html(a, rs, study_by_name, note_by_key) for a, rs in sorted(by_article.items())}, f,
                  ensure_ascii=False, indent=0)


def main():
    if len(sys.argv) > 1:
        merge(sys.argv[1:])
    toc = load_toc()
    expected = expected_notes(toc)
    rows = load_rows(expected)

    notes = []
    for k, (art, s, a, meta) in expected.items():
        r = rows[k]
        notes.append({
            "key": k, "article": art, "title": meta["title"], "set": s, "id": a["id"],
            "quote": a.get("quote"), "book": meta["book"], "sequence": meta["sequence"],
            "sequence_title": meta["sequence_title"], "target": r["target"],
            "source": (r.get("source") or "").strip() or None, "verdict": r["verdict"],
            "stance": r.get("stance"), "mode": r.get("mode"), "gist": r.get("gist", ""),
        })
    skeptic = [n for n in notes if n["set"] in SKEPTIC_SETS]
    rebuttal = [n for n in notes if n["set"] in REBUTTAL_SETS]

    # --- Cited studies: those the essays cite, deduplicated by name --------------
    note_by_key = {n["key"]: n for n in notes}
    meta_by_article = {n["article"]: n for n in notes}
    cites = load_essay_studies(note_by_key)
    by_source = collections.defaultdict(list)
    for r in cites:
        by_source[r["study"]].append(r)
    studies = []
    for src, rs in by_source.items():
        # Each note's verdict here is on this study, which may differ from the note's overall verdict.
        ns = [dict(note_by_key[a["note"]], verdict=a["verdict"]) for r in rs for a in r["assessments"]]
        if ns:
            groups = collections.Counter(GROUP[n["verdict"]] for n in ns)
            top = max(groups.values())
            # Majority group; ties go to the middle ("open"), then to "damaged".
            group = next(g for g in ("open", "damaged", "stands") if groups.get(g) == top) \
                if list(groups.values()).count(top) > 1 else groups.most_common(1)[0][0]
            vs = collections.Counter(n["verdict"] for n in ns if GROUP[n["verdict"]] == group)
            verdict = max(vs, key=lambda v: (vs[v], -VERDICTS.index(v)))
        else:
            groups, group, verdict = {}, "unassessed", "unassessed"
        studies.append({
            "source": src, "verdict": verdict, "group": group,
            "books": sorted({meta_by_article[r["article"]]["book"] for r in rs}, key=BOOKS.index),
            "conflict": len(groups) > 1,
            "cited_in": [{"article": r["article"], "title": meta_by_article[r["article"]]["title"],
                          "footnote": r["footnote"]} for r in rs],
            "notes": [{"set": n["set"], "id": n["id"], "verdict": n["verdict"], "gist": n["gist"],
                       "article": n["article"], "title": n["title"]} for n in ns],
        })
    studies.sort(key=lambda s: (STUDY_VERDICTS.index(s["verdict"]), s["source"].lower()))

    study_fate = {"all": counter_dict(collections.Counter(s["verdict"] for s in studies), STUDY_VERDICTS)}
    for b in BOOKS:
        # A study cited in two books counts in each.
        study_fate[b] = counter_dict(collections.Counter(s["verdict"] for s in studies if b in s["books"]),
                                     STUDY_VERDICTS)

    # --- Skeptic notes by target and by sequence ------------------------------
    target_x_verdict = {t: counter_dict(collections.Counter(n["verdict"] for n in skeptic if n["target"] == t), VERDICTS)
                        for t in TARGETS}
    seqs = collections.OrderedDict()
    for n in sorted(skeptic, key=lambda n: (BOOKS.index(n["book"]), n["sequence"] == "interlude", n["sequence"])):
        key = (n["book"], n["sequence"])
        seqs.setdefault(key, {"book": n["book"], "sequence": n["sequence"],
                              "title": n["sequence_title"], "articles": set(), "verdicts": collections.Counter()})
        seqs[key]["articles"].add(n["article"])
        seqs[key]["verdicts"][n["verdict"]] += 1
    sequences = [{"book": v["book"], "sequence": v["sequence"], "title": v["title"],
                  "articles": len(v["articles"]), "notes": sum(v["verdicts"].values()),
                  "verdicts": counter_dict(v["verdicts"], VERDICTS)} for v in seqs.values()]
    set_x_verdict = {s: counter_dict(collections.Counter(n["verdict"] for n in skeptic if n["set"] == s), VERDICTS)
                     for s in SKEPTIC_SETS}

    # --- Fable vs rebuttal pairs ---------------------------------------------
    fable_by_quote = {(n["article"], n["quote"]): n for n in skeptic if n["set"] == "fable" and n["quote"]}
    pairs, unpaired = [], []
    for r in rebuttal:
        f = fable_by_quote.get((r["article"], r["quote"]))
        if not f:
            # Whole-article notes carry no quote; pair them with the quote-less Fable note of the same id.
            f = next((n for n in skeptic if n["set"] == "fable" and n["article"] == r["article"]
                      and not n["quote"] and n["id"] == r["id"]), None)
        if not f:
            unpaired.append(r["key"])
            continue
        pairs.append({
            "article": r["article"], "title": r["title"], "book": r["book"], "sequence": r["sequence"],
            "quote": r["quote"], "fable_id": f["id"], "fable_verdict": f["verdict"], "fable_gist": f["gist"],
            "target": f["target"], "set": r["set"], "id": r["id"], "stance": r["stance"], "mode": r["mode"],
            "verdict": r["verdict"], "gist": r["gist"],
        })
    if unpaired:
        die(f"{len(unpaired)} rebuttal notes share no quote with a Fable note, e.g. {unpaired[:5]}")

    rebuttals = {}
    for s in REBUTTAL_SETS:
        ps = [p for p in pairs if p["set"] == s]
        rebuttals[s] = {
            "n": len(ps),
            "books": sorted({p["book"] for p in ps}, key=BOOKS.index),
            "stance_by_book": {b: counter_dict(collections.Counter(p["stance"] for p in ps if p["book"] == b), STANCES)
                               for b in BOOKS if any(p["book"] == b for p in ps)},
            "mode": counter_dict(collections.Counter(p["mode"] for p in ps), MODES),
            "fable_verdict_x_stance": {v: counter_dict(collections.Counter(p["stance"] for p in ps if p["fable_verdict"] == v), STANCES)
                                       for v in VERDICTS},
            "target_x_stance": {t: counter_dict(collections.Counter(p["stance"] for p in ps if p["target"] == t), STANCES)
                                for t in TARGETS},
        }

    # Sharpest disagreements: Fable says damaged, the rebuttal contests outright
    # and its implied verdict is that the claim stands.
    sharp = [p for p in pairs if GROUP[p["fable_verdict"]] == "damaged" and p["stance"] == "contests"
             and GROUP[p["verdict"]] == "stands"]
    sharp.sort(key=lambda p: (REBUTTAL_SETS.index(p["set"]), BOOKS.index(p["book"]), p["sequence"], p["title"]))

    # The two rebuttal passes answering the same Fable note (Book I).
    by_fable = collections.defaultdict(dict)
    for p in pairs:
        by_fable[(p["article"], p["fable_id"])][p["set"]] = p
    both = [v for v in by_fable.values() if len(v) == len(REBUTTAL_SETS)]
    rebuttal_agreement = {
        "n": len(both),
        "matrix": {a: counter_dict(collections.Counter(v[REBUTTAL_SETS[1]]["stance"] for v in both
                                                       if v[REBUTTAL_SETS[0]]["stance"] == a), STANCES)
                   for a in STANCES},
        "split": [{"article": v[REBUTTAL_SETS[0]]["article"], "title": v[REBUTTAL_SETS[0]]["title"],
                   "fable_gist": v[REBUTTAL_SETS[0]]["fable_gist"],
                   **{s: {"stance": v[s]["stance"], "gist": v[s]["gist"]} for s in REBUTTAL_SETS}}
                  for v in both if {v[s]["stance"] for s in REBUTTAL_SETS} == {"concedes", "contests"}],
    }

    # Studies the skeptic passes disagree on.
    skeptic_conflicts = [s for s in studies if s["conflict"] and len({n["set"] for n in s["notes"]}) > 1]

    stands = sum(1 for s in studies if s["group"] == "stands")
    summary = {
        "generated": datetime.date.today().isoformat(),
        "sets": {"skeptic": SKEPTIC_SETS, "rebuttal": REBUTTAL_SETS},
        "verdicts": VERDICTS, "groups": GROUP, "targets": TARGETS, "stances": STANCES, "modes": MODES,
        "study_verdicts": STUDY_VERDICTS,
        "totals": {
            "notes": len(notes), "skeptic_notes": len(skeptic), "rebuttal_notes": len(rebuttal),
            "articles": len({n["article"] for n in notes}),
            "studies": len(studies), "studies_stand": stands,
            "studies_assessed": sum(1 for s in studies if s["group"] != "unassessed"),
            "studies_damaged": sum(1 for s in studies if s["group"] == "damaged"),
            "by_set": {s: sum(1 for n in notes if n["set"] == s) for s in SETS},
            "skeptic_groups": counter_dict(collections.Counter(GROUP[n["verdict"]] for n in skeptic),
                                           ["stands", "open", "damaged"]),
        },
        "study_fate": study_fate,
        "studies": studies,
        "target_x_verdict": target_x_verdict,
        "set_x_verdict": set_x_verdict,
        "sequences": sequences,
        "rebuttals": rebuttals,
        "sharp_disagreements": sharp,
        "rebuttal_agreement": rebuttal_agreement,
        "skeptic_conflicts": skeptic_conflicts,
    }
    with open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    write_index_bars(study_fate)
    write_toc_pies(studies, cites, note_by_key)
    t = summary["totals"]
    print(f"{t['notes']} notes ({t['skeptic_notes']} skeptic, {t['rebuttal_notes']} rebuttal) in {t['articles']} articles")
    print(f"{t['studies']} distinct cited studies ({t['studies_assessed']} assessed): "
          f"{stands} stand, {t['studies_damaged']} damaged")
    print(f"{len(pairs)} rebuttal pairs, {len(sharp)} sharp disagreements, "
          f"{rebuttal_agreement['n']} Fable notes answered by both rebuttal sets")
    print(f"wrote {os.path.relpath(SUMMARY, ROOT)}")


if __name__ == "__main__":
    main()
