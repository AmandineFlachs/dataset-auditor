# Roadmap

dataset-auditor is **`v0.2.0`**. The `v0.1.0` core — the check families plus one
self-contained HTML report, working across more than one dataset, with the live local-LLM
features run against a real server — is built. `v0.2.0` adds a **leakage-safe evaluation layer
and a readiness rubric**. This page records **what has been done**, in build order, then the
ideas deliberately parked for later. The benchmark has since been **published to Kaggle** as a
public, cross-model leaderboard (see below).

## Done so far

### Multi-dataset support ✅

Dataset-specific knowledge lives in a `DatasetSpec` registry (`auditor.datasets`);
the loader and checks read it, so a new dataset is one spec + its rules, with no
engine changes. Flagship: LeMat-Bulk.

### Phase 3 — LLM foundation + four generic checks ✅

The guiding principle is unchanged: every check is a **generic engine** configured by
a `DatasetSpec`, never bound to one dataset. Domain-specific logic is opt-in and
dormant by default (the `null_island` precedent), so meteorites and any future dataset
keep working. In build order:

1. **Foundation — `auditor.llm`. ✅** A thin client for the local vLLM
   `/v1` endpoint, with a `judge(prompt, schema)` helper that returns validated
   objects and injects `spec.domain_context` as grounding. **Graceful
   degradation is a hard requirement:** if the server is offline the LLM checks
   emit one `info` finding and the deterministic suite runs unaffected. Tests
   mock the client, so CI needs no live server.
2. **Generic group-consistency — `checks/consistency.py`. ✅** Engine:
   *rows that share a key should agree.* Two modes — `exact` (a supposedly
   invariant column must be identical across the group) and `numeric` (a value
   must agree within a tolerance, optionally per-unit). On LeMat-Bulk the same
   `immutable_id` recurs once per DFT functional, so the rule asserts those rows
   share identical **structure** (`nsites`, `nelements`, the three formulas, the
   element list). A physics correction made during the build: DFT total energies
   are **not** comparable across exchange-correlation functionals (PBE / PBEsol /
   SCAN have different references), so the originally-planned "conflicting
   energies across functionals" finding was dropped — that spread is expected
   behaviour, not a defect, and flagging it would be a false-positive generator.
   The structural rule is honestly clean on the current sample; a crafted-defect
   test proves it fires. (LLM ranking deferred: with no real findings to triage,
   there is nothing yet for it to rank.)
3. **Generic capabilities — `near_dup.py`, `pii.py`, `labels.py`. ✅**
   - **Near-duplicate — `near_dup.py`.** Inverse of consistency: *same
     content, different identity = probably one entity recorded twice.* The
     **exact (hash-collision) tier** groups by a content key. On LeMat-Bulk that
     is `entalpic_fingerprint` vs `immutable_id`, and unlike most generic checks
     it **fires on the real sample**: 240 rows / 119 fingerprint groups are one
     structure ingested under several provenance ids — the genuine harmonization
     signal. The fuzzy embedding tier (sentence-transformers) is the deferred
     extension; it needs a heavy model and barely fits these scientific columns.
   - **PII — `pii.py` (regex tier).** Dependency-free patterns for
     emails, SSNs, Luhn-checked cards, phones, IPv4, with **masked evidence** so the
     report does not itself leak. It **always runs**: declared `pii_text_columns` get
     every detector; with none declared it auto-detects the text columns and scans them
     for the rigid identifiers (email, SSN) only — so privacy is never a blind spot while
     numeric science columns stay safe from false positives. Both flagships come back
     clean. Presidio NER and an LLM pass are the deferred escalation.
   - **Categorical plausibility — `labels.py`.** Label-noise reframed: the
     LLM judges whether a categorical value is plausible given the row + domain
     context. The first consumer of `auditor.llm`. Emits `labels.implausible` (WARN),
     `labels.uncertain` (low-confidence INFO), `labels.out_of_vocab` (deterministic,
     no LLM call), and exactly one `labels.skipped` INFO when the server is offline.
     Samples distinct (value, context) cases within a cap; degrades gracefully up
     front and mid-run; wired lazily so a bare `import auditor.checks` stays
     httpx-free. Both flagships leave `label_rules` empty (their categoricals are
     facts), so it is silent on real data and proven on a mocked-client fixture.
4. **Opt-in domain pack — formula agreement. ✅** The one genuinely
   materials-specific check: parse the three OPTIMADE formula columns to a
   canonical composition and flag disagreement (plus the `elements` list and
   `nelements` count as cross-checks). A genuine mismatch is an `error` — these
   are redundant encodings of one composition, so disagreement is an internal
   contradiction. Dormant unless a spec sets `formula_rules`, so it never touches
   meteorites. It turned out to need **no chemistry dependency**: the columns have
   a trivial, regular OPTIMADE grammar and the check compares them against *each
   other*, not external chemistry, so a small stdlib parser (symbols + counts +
   GCD) is the honest tool and keeps the pack as dep-light as `schema.py`. Like
   `consistency.py` it is clean on the real sample (all 25k rows agree); a
   crafted-defect test proves it fires.

### Compound-engineering hardening pass ✅

A multi-agent review (parallel reviewers per lens → adversarial verification)
surfaced 11 confirmed issues; the real ones were fixed and pinned with tests: the
`duplicates` `key=None` disable contract (was silently reusing the meteorite key),
NaN keys no longer flagged as duplicate errors, defensive numeric coercion in
`units`, a divide-by-zero `inf` guard in `consistency`, a clear error on
column-name collisions in `load`, tidier PII evidence, plus boundary/edge tests
across the suite.

### Phase 4 — self-contained HTML report ✅

The HTML report (`auditor.report`, Jinja2 → one self-contained `report.html`).
Beyond rendering `Finding` objects it earns its keep on real audits:

- **Aggregates identical findings** — findings sharing a signature (field,
  message, evidence, expected, fix, severity) collapse to one line with a count +
  sample row ids, so the meteorite set's 6,214 null-island rows become a single line.
- **Groups by check** most-severe-first, then **caps distinct rows** per check with
  an honest "+ N more"; counts stay complete.
- **Found → Expected.** Each `Finding` carries an optional `expected`; the checks
  with a concrete target populate it (range bounds, uniqueness, null threshold,
  allowed vocab, the formula anchor, shared-key agreement), so the row shows a red
  Found → green Expected pair. Judgement-style checks (near-dup, PII, model-judged
  labels, unparseable formulas) leave it `None` and fall back to Evidence → Fix.
- **Reference panels** (when passed the DataFrame): a Dataset-overview profile
  (shape, per-column null rates, categorical value-counts) and a Findings-by-column
  cross-cut, kept as collapsed reference at the foot of the stream.
- Inline CSS, **no external resources** (system fonts), evidence autoescaped. Sample
  reports for both flagships live in `examples/`. Run:
  `python -m auditor.report --dataset lemat_bulk --out report.html`.

### Phase 4.5 — Triage redesign (from a Claude Design handoff) ✅

The report was rebuilt into a **Triage** layout: a top appbar, a left **category
rail** (one entry per check with count + severity distribution bar), and a **stream**
led by a **summary strip** (total issues, per-severity counts, clean-rate). Each issue
is an expandable row; search, single-select severity chips, and category filtering are
vanilla JS. A per-issue **triage worklist** (keep / dismiss / needs-review + a note)
persists in the browser (`localStorage`, keyed by a content hash so decisions survive
regeneration) and **exports to CSV**. Light only, fully self-contained.

### Phase D — live local-LLM runs (2026-06-07) ✅

`auditor.research` + the `auditor brief` command write a domain briefing (column
meanings, plausible ranges, pitfalls, *advisory* suggested checks) from **metadata
only — never raw rows**. `auditor triage` ranks findings by a **deterministic**
priority and has the model add a neutral summary + a "what to check" line per issue
(it is *not* asked for a real-vs-expected verdict, the most error-prone call). Both
degrade gracefully when no server is up. These runs use **vLLM**
(OpenAI-compatible `/v1`) serving **Qwen3-4B** locally; a small model is enough for the
advisory-only role. The live runs exposed a VRAM-paging gotcha (fixed with a lower
`--gpu-memory-utilization`) and honest model errors (it still mis-guesses some column
meanings, e.g. `chemical_formula_anonymous`) that reinforce the advisory-only framing.

### Phase 5 — packaging + ship ✅

CLI (`run`, `datasets`, `profile`, `brief`, `triage`), docs, the
deterministic-vs-LLM README section, a CHANGELOG, README screenshots of the report,
an MIT `LICENSE`, and the repo under version control. Shipped publicly and tagged `v0.1.0`.

### v2 — leakage-safe evaluation + readiness rubric ✅ (`v0.2.0`)

A first v2 attempt (a Kaggle-benchmark layer + a `capture`/`select-model` self-improving
loop) was **removed**: the `triage-verdict` benchmark *leaked* (its domain-context grounding
stated the answers, measuring reading not reasoning), and the loop was *unproven* (tiny
N≈5–17, no experiment). Rather than ship a number we couldn't defend, it was cut and the
eval layer rebuilt **scientifically**. `main` stays v1; this work lives on branch `v2`.

What v2 adds:

1. **Evaluation protocol first** — `EVAL_PROTOCOL.md` (scope tiers, leakage/contamination
   definitions, dev/calibration/hidden splits, prompt- and scoring-freeze, held-out-only
   reporting with confidence intervals + baselines), plus `docs/methodology.md` and
   `docs/leakage_checklist.md`.
2. **Leakage-safe benchmark, local-only (no Kaggle SDK).** A pure model-free harness
   (`benchmarks/shared/`) + two tasks that reuse the shipped `build_label_prompt` /
   `LabelVerdict` but pass **no** answer-bearing context: `labels_plausibility`
   (phase-at-STP) and `element_classification` (metal/nonmetal/metalloid). Three disjoint
   splits each, balanced classes, an automated leakage linter, a frozen-prompt hash, and a
   value↔label decorrelation guard — all enforced in CI.
3. **Reasoning mode.** The strict (forced-JSON) path made the small Qwen3-4B confabulate
   and score at the floor (0.500 held-out, 0/20 defects). Letting it *think* first
   (opt-in `reasoning` in `auditor.llm`, default-on for the `labels` check) took it to
   **1.000 held-out on both domains** (80/80 each, 95% CI [0.954, 1.000]), beating the
   vocabulary/majority floors.
4. **Readiness rubric** — `auditor rubric` + a report panel: per-dimension scores
   (completeness/consistency/plausibility/duplication/privacy) + overall, a deterministic
   roll-up of the findings; LLM-judged labels stay advisory and never move a score.

Held-out sets were grown 40 → **80 per task** (CI tightened to [0.954, 1.000]). A second model
(Qwen3.5-0.8B) was then tried as a contrast: it sits **below the harness's structured-output
floor** — it echoes the schema instead of a verdict, so it cannot complete the benchmark under
the frozen prompt. A side-probe confirms it knows the chemistry; the verbose schema-in-prompt is
the limiter. The frozen prompt was *not* relaxed to rescue a score (that would tune on held-out
data), so the honest result is "4B reasoning 1.000; 0.8B non-compliant." Enough to defend the
core claim, so further model sweeps are deferred (see below).

Status: built and **held-out-verified on Qwen3-4B** (223 tests pass). Shipped as `v0.2.0`.

## Deferred — what's next

Parked on purpose: this is scoping without creep, and each item notes *why* it waits.

- **Publish the proven benchmark to Kaggle — ✅ done.** Both domains ship as Kaggle Benchmarks
  tasks (see [`kaggle/`](kaggle/)), each as an *open* set (the public cases) and a *fresh-private*
  set (newly minted, never published — disjoint from all public splits by a minimal-context
  projection — so a leaderboard score can't be memorisation). Published with
  `--no-publish-backing-notebook` on the private tasks so the answer key stays server-side. The
  leakage discipline carries over: byte-identical frozen prompt (SHA-verified at generation),
  exact-match scoring, the vocabulary/majority baselines as the 0.5 floor. Each task is a single
  run per model returning `(accuracy, 95% CI)`. **Cross-model result:** Claude Haiku 4.5 = 1.000
  across all four; Gemini 3 Flash 0.90–1.000; Qwen3-Next-80B **Thinking 1.000 vs Instruct 0.513**
  on phase (the reasoning thesis, live across vendors); the benchmark discriminates and the
  private set tracks the open one. The original "import wall" dissolved — each task file is
  self-contained (no `auditor` import), generated by `kaggle/build_open_tasks.py`.
- **More eval depth is deferred as gold-plating** (decided 2026-06-14). The core claim — the
  advisory LLM label check is trustworthy — is already defended (reasoning-mode 1.000, held-out,
  leakage-safe, N=80, baselines beaten). So: *more models* (low marginal value; memorization is
  defended structurally, and the 0.8B "can't comply" point already exists) and a *second kind of
  task* (calibration would validate the advisory-only `confidence` field; an LLM-as-judge task
  imports a model-grading-model trust dependency) both wait until there's a concrete reason to
  reopen them.
- **The self-improving loop stays out** unless revived with an actual experiment showing it
  improves model selection (its history is on `v2-kaggle-benchmarks`).

- **Config-file rules.** Plausibility rules now live per-dataset in
  `datasets.py` (in-code `DatasetSpec.range_rules`), not scattered through the
  checks. Loading them from YAML/JSON (so non-coders can add rules) is the next
  step and remains deferred.
- **Fuzzy near-duplicate tier.** The exact hash-collision tier ships; the
  embedding-based tier (sentence-transformers) waits for a dataset whose text
  columns actually need it — it is heavy and barely fits the current scientific
  columns.
- **PII escalation.** The regex tier ships; Presidio NER and an LLM pass wait
  for a dataset with real free-text columns (neither flagship has any).
- **Unit-string drift detection** (e.g. mixed `"5 kg"` / `"5000 g"`, `"°C"` /
  `"K"`). No target in the current datasets, so not built yet. Belongs in
  `units.py` when a dataset needs it.
- **Type-mismatch / format checks in `schema.py`** (numbers stored as strings,
  mixed-type columns, regex format validation for IDs/dates).
- **A plugin system for checks.**
- **CLI config files and check selection beyond simple flags.**
- **Streamlit front-end** for uploading a CSV and viewing the report in-browser.
