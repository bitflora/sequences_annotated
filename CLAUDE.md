# Sequences — Skeptic's Edition

HTML edition of Eliezer Yudkowsky's "Rationality: From AI to Zombies" with a skeptic's annotation overlay.

## Annotation system

Annotations are kept entirely separate from the original article HTML. The original files are not modified beyond two additions in `<head>`:
- `<link rel='stylesheet' href='wiki/pub/skins/readthesequences/annotations.css' type='text/css' />`
- `<script src="wiki/pub/skins/readthesequences/annotations.js" defer></script>`

No other changes to the original HTML. The JS injects all markers at runtime.

### Annotation data files

Each article can have multiple independently-contributed annotation sets (e.g. one per model/author), selectable by the reader at runtime.

`annotations/<ArticleName>.index.json` — lists the annotation sets available for that article:
```json
[
  { "id": "opus", "label": "Opus", "code": "O", "file": "annotations/<ArticleName>.opus.json", "default": true }
]
```
- `id`: stable slug for the set; used as the localStorage preference key and to namespace element ids. Keep it consistent for the same contributor across articles (e.g. always `"opus"`, `"sonnet"`).
- `label`: shown in the reader-facing toggle panel.
- `code`: short (1-2 char) tag used to prefix marker numbers (e.g. `[O1]`) when more than one set is enabled at once. Falls back to the first letter of `id` if omitted.
- `file`: path to that set's annotation JSON.
- `default`: whether the set is shown out of the box, before the reader has made an explicit choice.

`annotations/<ArticleName>.<setId>.json` — the annotation objects for one set, e.g. `annotations/Availability.opus.json`.

Structure:
```json
[
  { "id": 1, "side": "left",  "quote": "exact plain text of the annotated phrase", "content": "<html string>" },
  { "id": 2, "side": "right", "quote": "another phrase to highlight",              "content": "<html string>" },
  { "id": 3, "side": "left",                                                        "content": "<html string>" }
]
```

- `id`: sequential integer *within this set*; combined with the set id to generate element ids (`annotation-<setId>-N`)
- `side`: odd ids → `"left"`, even ids → `"right"` (alternating convention)
- `quote` *(optional)*: plain text substring to locate in the article. The JS finds this text, wraps it in `<span class="annotation-target">`, and inserts a `<sup class="annotation-ref">` marker after it. Omit for annotations that comment on the article as a whole rather than a specific passage.
- `content`: HTML string for the margin note; use `<a href="https://doi.org/...">Author et al. (YEAR)</a>` for citations

The `quote` must be an exact plain-text substring of the article as it appears in the DOM (ignore HTML tags; match the text content). If the phrase contains inline elements like `<em>`, write the plain text without them.

Most annotations across all articles are attributed to the `opus` set (label "Opus"). Book I sequences A, B, C and D and Book III sequences L and M additionally carry a `fable` set (label "Fable", code "F"), a deliberately adversarial pass that challenges the essays' reasoning and cited studies; it is `default: true` alongside Opus where both exist.

### Layout

`annotations.css` widens `#wikitext` to 1540px with 460px padding each side, leaving a 620px content column flanked by 420px gutters. `annotations.js` fetches the index, then fetches whichever sets are enabled, injects inline markers via `quote` matching, creates `<aside class="margin-note left|right">` elements inside `#wikitext`, and positions them vertically (absolute, `top` set by JS) to align with their reference superscripts. Collisions are resolved by pushing later notes downward.

A small "Annotations ▾" toggle panel (fixed, top-right) lists every set from the index with a checkbox; the reader's choices are stored in `localStorage` under `seq-annotation-sets` (an object of `setId -> boolean`) and apply across articles. Toggling re-fetches and re-renders in place.

Below 1000px viewport width the margin notes are hidden and the layout collapses to the normal single-column skin; the toggle panel still shows.

If `<ArticleName>.index.json` doesn't exist, the JS falls back to fetching `annotations/<ArticleName>.json` directly as a single always-on set with no toggle (legacy/unmigrated articles).

### Adding annotations to a new article

1. Add the two `<head>` tags above to the article HTML (after the existing `skin.css` link)
2. Create `annotations/<ArticleName>.index.json` with at least one set entry, and `annotations/<ArticleName>.<setId>.json` with the annotation objects — no changes to the article body needed

### Adding a new contributor's annotation set to an already-annotated article

1. Pick a stable `setId` (e.g. `"sonnet"`) — reuse it across every article that contributor annotates
2. Create `annotations/<ArticleName>.<setId>.json` with that contributor's annotation objects (own independent `id` sequence starting at 1)
3. Append an entry for it to `annotations/<ArticleName>.index.json`; set `"default": false` unless it should be shown out of the box

### Scripts

`scripts/extract_annotations.py` — migrates the old bottom-block format to JSON. Run if any article still has a `<div class="skeptic-annotations">` block:
```bash
python3 scripts/extract_annotations.py          # all git-modified HTML files
python3 scripts/extract_annotations.py Foo.html # specific file
```

`scripts/migrate_to_quote_anchors.py` — one-time migration that extracted `quote` fields from inline `<span class="annotation-target">` markers and stripped those markers from the HTML. Already run; kept for reference.

### Annotation style guide

- Be scholarly and direct, not snarky
- Each annotation: state the claim → what research originally showed → what subsequent research found or what the logical problem is
- 3–5 sentences per annotation
- Challenge the *reasoning*, not just the effect size: where does the evidence not support the strong conclusion?
- Positive annotations ("this effect is robust") are fine and useful
- Cite real DOIs; flag when a citation is a book with no DOI

### Current coverage

Book I ("Map and Territory", 46 articles) has 35 annotated articles. The remaining 11 were skipped because they contain no citable empirical claims (philosophical parables, pure Bayesian math, personal narrative).

The `fable` set covers every article in Book I sequence A ("Predictably Wrong", 10 articles), 31 annotations total, including Feeling Rational, which Opus skipped. Its targets: the VNM axioms and ecological rationality against "rationality = expected utility"; the Hertwig/Gigerenzer frequency-format dispute on the conjunction fallacy (in both What Do I Mean and Burdensome Details, plus Tentori & Crupi and support theory); bidirectional emotion–belief causation and the positive-illusions/depressive-realism literature against "truth nourishes"; the technology-before-science history against the Baconian origin story; WEIRD sampling and Gigerenzer's norm critique against "humanly universal" biases; Mercier & Sperber's argumentative theory as the sequence's own guessed mechanism with the opposite prescription; the misattributed Kates quotation and the flood-insurance/levee incentive evidence; implementation intentions, combined inside/outside view, and Flyvbjerg's strategic misrepresentation on the planning fallacy; the June/Jane slip, the overhearers' own miscalibration, and the false Chamberlain anecdote; cumulative culture and epistemic vigilance against the "universal knowledge" ancestral premise and the deficit model; rat metacognition, cognitive impenetrability, the bias blind spot and the debiasing literature against the "reflective correction" promise.

The `fable` set covers every article in Book I sequence B ("Fake Beliefs", 9 articles), 43 annotations total, including the three essays Opus skipped (Professing and Cheering, Belief as Attire, Applause Lights). Its targets: verificationism the essays disown and then reuse; historical claims that are checkable and false (phlogiston "made no predictions", the Old Testament has "no wonder at the universe", Rome "enforced religious tolerance", the New Testament avoids showy miracles, non-overlapping magisteria is "recent and Western"); replication failures and reversals (backfire effect, expressive responding, secularization thesis); the pre-existing literatures the essays ignore (Sperber's reflective belief, alief, religious credence, the anthropology of neopaganism, Tetlock's foxes, the wisdom literature, glittering generalities); AI predictions the LLM era emptied (Bayesian Judo); and the essays' own single-anecdote, mind-reading evidence base.

The `fable` set also covers every article in Book I sequence C ("Noticing Confusion", 9 articles), 37 annotations total, including the three Opus skipped (What Is Evidence?, How Much Evidence Does It Take?, Einstein's Arrogance). Its targets: the Einstein quote's actual provenance (Rosenthal-Schneider, after the result) and the Entwurf theory Einstein got wrong first; the 1919 eclipse data quality; Solomonoff's reference-machine circularity (Sterkenburg 2016); the arithmetic slip (125, not 131 losing tickets) and the unstated independence assumption (Sally Clark); mutual information vs. likelihood ratio; belief contagion as information cascade; tacit knowledge (Collins's Q of sapphire); the internal contradiction between Scientific Evidence ("why bother to run the experiment") and Einstein's Arrogance; reproducibility as nominal property (OSC 2015, Errington 2021); EMS non-transport rates and missed-MI rates behind the IRC anecdote; Spinozan belief model counter-evidence; the invalid miracles application of conservation of expected evidence and the "sit back and relax" moral vs. Lindley/Good; preregistration adherence; Klayman & Ha on positive testing; hindsight effect size; surprisingness predicting non-replication (Dreber 2015, Camerer 2018); and introspective debiasing that the literature found ineffective.

The `fable` set also covers every article in Book I sequence D ("Mysterious Answers", 16 articles), 50 annotations total, including the three Opus skipped (Failing to Learn from History, Explain/Worship/Ignore?, Truly Part of You). Its targets: the founding metal-plate anecdote sourced to a joke file; "false" conflated with "empty" throughout (heat conduction, phlogiston yet again, Kelvin's vitalism as a testable thermodynamic claim, the Wöhler chronology reversed); the "no moving parts" sign condemning the gene, caloric, the ether and the neutrino; emergence's technical content (Anderson, Laughlin & Pines, Bedau) and "emergent abilities" in LLMs; scaling and the Rubik's-cube solver as hindsight on Say Not "Complexity"; Klayman & Ha and the DAX/MED framing on the 2-4-6 task; probability matching under incentives (Shanks 2002) and mixed strategies/SGD against "never randomize"; Tegmark falsifying Orch-OR by Traditional means; the uniqueness thesis and the catch-all hypothesis problem; the causal Markov condition violations and NP-hardness of exact inference against the Bayes-net story of cognition; imagination inflation and historical-analogy pathologies against "making history available"; the curiosity literature (Loewenstein, Kang) reversing the curiosity-stopper claim; Kripke/Putnam against the Davidsonian beavers; and the regeneration test as untested self-report.

Book II ("How to Actually Change Your Mind") has 18 annotated articles, covering its empirically-grounded essays: Correspondence Bias, Anchoring and Adjustment, Priming and Contamination, The Affect Heuristic, Evaluability, Unbounded Scales/Jury Awards, The Halo Effect, Asch's Conformity Experiment, The Robbers Cave Experiment, Knowing About Biases Can Hurt People, Do We Believe Everything We're Told?, We Change Our Minds Less Often Than We Think, Hold Off On Proposing Solutions, Cached Thoughts, Lonely Dissent, Evaporative Cooling of Group Beliefs, Policy Debates Should Not Appear One-Sided, and On Expressing Your Concerns. The remaining essays were skipped as containing no citable empirical claims (Bayesian/logic pieces, self-deception philosophy, cult sociology and political commentary, parables, personal narrative).

Book III ("The Machine in the Ghost") has 8 annotated articles, covering the essays with citable empirical claims: An Alien God (inverted-retina design), Evolving to Extinction (bystander effect, Fisher's sex-ratio principle), The Tragedy of Group Selectionism (multilevel selection revival, Wade's Tribolium experiments), Adaptation-Executers Not Fitness-Maximizers (proximate/ultimate distinction, EEA assumptions), Evolutionary Psychology (Stroop effect, mate-preference just-so stories), An Especially Elegant Evolutionary Psychology Experiment (Crawford et al. grief correlation), Superstimuli and the Collapse of Western Civilization (ego depletion replication failure, supernormal stimuli), and Typicality and Asymmetrical Similarity (prototype effects, Tversky asymmetry). Most of "A Human's Guide to Words" (N) was skipped as linguistic philosophy, parable, and information-theory math.

The `fable` set covers every article in Book III sequences L ("The Simple Math of Evolution", 13 articles) and M ("Fragile Purposes", 10 articles), 100 annotations total, including the essays Opus skipped as non-empirical. Its brief is maximum skepticism: unsourced numbers, evolutionary just-so stories, replication failures (ego depletion, Ekman universals, bystander effect in the field, optimism bias), claims contradicted by later evidence (thrifty gene, Framingham selection on weight, gaming-disorder prevalence, NCLB effects), and predictions about AI development that the subsequent history of machine learning falsified (Artificial Addition, Ghosts in the Machine, The Power of Intelligence). It also flags where the essays' own method (don't reason from what would be a satisfying story) is violated by their examples (Uglak, group-selectionist psychology, willpower just-so stories).

Book IV ("Mere Reality") has 5 annotated articles, covering the essays with citable empirical/methodological claims: Outside the Laboratory (intelligence/rationality dissociation, scientists' religiosity surveys, compartmentalization), Beautiful Probability (likelihood principle, optional stopping vs. the replication crisis), The Second Law of Thermodynamics and Engines of Cognition (Landauer's principle confirmation, the contested Maxwell's-demon exorcism, Jaynes/MaxEnt as a minority interpretation), Scarcity (reactance, Cialdini's vivid-but-fragile demonstrations), and Many Worlds, One Best Guess (physicist-opinion polls, the unsolved Born-rule problem, decoherence not solving measurement). The bulk of Book IV was skipped as non-empirical: the physics-fact and physics-interpretation essays (Lawful Truth O, much of Quantum Physics S), the philosophy of mind / consciousness essays (Physicalism 201 R: zombies, qualia), the reductionism philosophy (Reductionism 101 P), the inspirational/personal essays in Joy in the Merely Real (Q), and the philosophy-of-science essays in Science and Rationality (T).
