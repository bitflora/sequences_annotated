#!/usr/bin/env python3
"""Validate analysis/findings.jsonl and aggregate it for Findings.html.

findings.jsonl holds one LLM-assigned classification per annotation in the
current sets (see findings_common.SETS). This script checks every row against
the annotation files, attaches book/sequence from Contents.html, pairs each
rebuttal note with the Fable note whose quote it shares, and writes
analysis/findings-summary.json.

Usage:
    python3 scripts/build_findings.py [FRAGMENT.jsonl ...]

With fragment paths, they are merged (in order) into analysis/findings.jsonl
first; without, the existing findings.jsonl is used.
"""
import collections
import datetime
import json
import os
import sys

from findings_common import (BOOKS, REBUTTAL_SETS, ROOT, SETS, SKEPTIC_SETS,
                             annotated_articles, article_meta, load_set, load_toc)

FINDINGS = os.path.join(ROOT, "analysis", "findings.jsonl")
SUMMARY = os.path.join(ROOT, "analysis", "findings-summary.json")
INDEX = os.path.join(ROOT, "index.html")

TARGETS = ["cited_study", "empirical_claim", "historical_fact", "attribution",
           "ai_prediction", "argument", "prior_work", "other"]
# Ordered from best to worst for the essay.
VERDICTS = ["holds", "holds_qualified", "contested", "unfalsifiable_or_na",
            "weakened", "failed_replication", "retracted_or_fraud", "false_or_misattributed"]
GROUP = {"holds": "stands", "holds_qualified": "stands",
         "contested": "open", "unfalsifiable_or_na": "open",
         "weakened": "damaged", "failed_replication": "damaged",
         "retracted_or_fraud": "damaged", "false_or_misattributed": "damaged"}
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


def counter_dict(c, keys):
    return {k: c.get(k, 0) for k in keys}


def write_index_bars(study_fate):
    """Rewrite the per-book cited-study bars between the <!-- studies:B --> markers in index.html."""
    with open(INDEX, encoding="utf-8") as f:
        page = f.read()
    for b in BOOKS:
        c = collections.Counter()
        for v, n in study_fate[b].items():
            c[GROUP[v]] += n
        total = sum(c.values())
        if total:
            segs = "".join(f'<span style="flex:{c[g]};background:var(--st-{g})"></span>'
                           for g in ("stands", "open", "damaged") if c[g])
            label = f"{c['stands']} of {total} cited studies hold up"
            extra = [f"{c['damaged']} damaged"] if c["damaged"] else []
            extra += [f"{c['open']} contested"] if c["open"] else []
            detail = " · ".join(extra)
            aria = label + (", " + ", ".join(extra) if extra else "")
            html = (f'<a class="book-studies" href="Findings.html" title="Cited studies in Book {b}">'
                    f'<span class="bar" role="img" aria-label="{aria}">{segs}</span>'
                    f'<span class="cap">{label}</span>'
                    + (f'<span class="cap">{detail}</span>' if detail else "") + '</a>')
        else:
            html = ""
        start, end = f"<!-- studies:{b} -->", f"<!-- /studies:{b} -->"
        i, j = page.find(start), page.find(end)
        if i < 0 or j < i:
            die(f"index.html has no {start} ... {end} markers")
        page = page[:i + len(start)] + html + page[j:]
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(page)


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

    # --- Cited studies, deduplicated by normalized source name ---------------
    by_source = collections.defaultdict(list)
    for n in skeptic:
        if n["target"] == "cited_study" and n["source"]:
            src = " ".join(n["source"].replace("&amp;", "&").split())
            by_source[SOURCE_ALIASES.get(src, src)].append(n)
    studies = []
    for src, ns in by_source.items():
        groups = collections.Counter(GROUP[n["verdict"]] for n in ns)
        top = max(groups.values())
        # Majority group; ties go to the middle ("open"), then to "damaged".
        group = next(g for g in ("open", "damaged", "stands") if groups.get(g) == top) \
            if list(groups.values()).count(top) > 1 else groups.most_common(1)[0][0]
        vs = collections.Counter(n["verdict"] for n in ns if GROUP[n["verdict"]] == group)
        verdict = max(vs, key=lambda v: (vs[v], -VERDICTS.index(v)))
        books = sorted({n["book"] for n in ns}, key=BOOKS.index)
        studies.append({
            "source": src, "verdict": verdict, "group": group, "books": books,
            "conflict": len(groups) > 1,
            "notes": [{"set": n["set"], "verdict": n["verdict"], "gist": n["gist"],
                       "article": n["article"], "title": n["title"]} for n in ns],
        })
    studies.sort(key=lambda s: (VERDICTS.index(s["verdict"]), s["source"].lower()))

    study_fate = {"all": counter_dict(collections.Counter(s["verdict"] for s in studies), VERDICTS)}
    for b in BOOKS:
        # A study cited in two books counts in each.
        study_fate[b] = counter_dict(collections.Counter(s["verdict"] for s in studies if b in s["books"]), VERDICTS)

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
        "totals": {
            "notes": len(notes), "skeptic_notes": len(skeptic), "rebuttal_notes": len(rebuttal),
            "articles": len({n["article"] for n in notes}),
            "studies": len(studies), "studies_stand": stands,
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
    t = summary["totals"]
    print(f"{t['notes']} notes ({t['skeptic_notes']} skeptic, {t['rebuttal_notes']} rebuttal) in {t['articles']} articles")
    print(f"{t['studies']} distinct cited studies: {stands} stand, {t['studies_damaged']} damaged")
    print(f"{len(pairs)} rebuttal pairs, {len(sharp)} sharp disagreements, "
          f"{rebuttal_agreement['n']} Fable notes answered by both rebuttal sets")
    print(f"wrote {os.path.relpath(SUMMARY, ROOT)}")


if __name__ == "__main__":
    main()
