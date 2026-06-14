# Evaluation Protocol

This document is **normative**. It defines what dataset-auditor measures, what it does
*not* measure, and the rules that keep an evaluation honest. The companion
[`docs/methodology.md`](docs/methodology.md) explains the *why*; this file states the
*rules*. The pre-freeze [`docs/leakage_checklist.md`](docs/leakage_checklist.md) is the
operational checklist derived from these rules.

The one principle behind everything here: **only ship claims that can be defended.**

---

## 1. Scope tiers

Every part of the system falls into exactly one tier.

| Tier | What it covers | Status of its output |
| --- | --- | --- |
| **Deterministic** | Every check id except `labels.*` — `schema.*`, `units.*`, `duplicates.*`, `consistency.*`, `near_dup.*`, `pii.*`, `formula.*`. The readiness rubric (`src/auditor/rubric.py`) is a deterministic *aggregation* of these. | **Facts.** Reproducible from the data alone, no model in the loop. Covered by `pytest`. |
| **Advisory** | The local LLM: `auditor brief`, the per-issue notes in `auditor triage`, and the `labels.*` check. | **Suggestions.** Never assert a hard error; never override a deterministic finding; degrade gracefully when no model is running. |
| **Benchmarked** | Exactly one task today: **label-plausibility** (`benchmarks/labels_plausibility/`). It measures the only fallible part — an LLM's judgement — under leakage-safe conditions. | **Measured claims**, and only as defined in §3–§5. |
| **Out of scope** | Anything not on a held-out test set; any claim about a model's general ability; the removed self-improving loop and real-vs-expected "verdict"; any benchmark task that has not passed the leakage checklist. | **Not claimed.** |

A capability moves from Advisory to Benchmarked only by adding a task that satisfies this
protocol. Nothing is claimed "reliable" on the strength of a demo.

---

## 2. Definitions

**Leakage** — any signal in the prompt or its context that lets the model produce the
right answer *without performing the reasoning under test*. The canonical example (and the
reason an earlier benchmark was deleted): grounding text that states the rule which decides
the answer. If a context-only shortcut can score well, the task leaks.

**Contamination** — the model has effectively seen the answer before. Two forms we guard
against: (a) **split contamination** — a test case was also used during prompt development
or threshold tuning; (b) **pretraining contamination** — a case is drawn verbatim from a
public source the model likely memorised. We prefer curated/planted cases over raw public
examples to limit (b), and enforce disjoint splits to eliminate (a).

**Held-out** — the test split, which is opened *only* for final reporting, after the
prompt and scorer are frozen.

---

## 3. Benchmark construction rules

1. **Reuse the shipped prompt.** A benchmark must call the exact production prompt builder
   (`auditor.checks.labels.build_label_prompt`) and output schema (`LabelVerdict`). A
   benchmark may not maintain its own copy — that would let the test and the product drift
   apart.
2. **No answer-bearing context.** The benchmark passes **no** `domain_context` and no
   context field that contains, implies, or lets the answer be trivially derived. Allowed
   context is an explicit allow-list in the task's `meta.json`.
3. **Curated/planted over raw.** Prefer deliberately constructed cases (a real entity with
   a planted-wrong label, or a confirmed-correct label) over scraped public rows.
4. **Balanced classes.** Each split is roughly 50/50 across the label classes so accuracy
   is meaningful and a majority guesser is a weak baseline.

---

## 4. Splits

Every benchmark task has three disjoint splits:

| Split | Used for | May be inspected during development? |
| --- | --- | --- |
| `dev` | Iterating on the prompt and the task framing. | Yes. |
| `calibration` | Tuning any thresholds (e.g. a confidence cut-off). | Yes. |
| `test` | **Final reporting only.** | **No** — opened once, after freezing. |

Rules:
- A case id (and its `(value, context)` signature) appears in **at most one** split.
  Enforced by `shared.cases.assert_disjoint_splits`, run in CI.
- `dev`/`calibration` cases are **never** reused for final scoring.
- The `test` split is opened only after §5 freezing, and the runner refuses to touch it
  without an explicit `--confirm-final` flag and a passing prompt-freeze check.

---

## 5. Freezing

**Prompt freeze.** Before the test split is run, the rendered prompt is frozen: its
identity hash (a SHA-256 over the builder, the schema, and the prompt template with case
values masked) is recorded in the task's `meta.json` and `PROMPT_FREEZE.md`. Because the
prompt comes from the shipped builder, *any* change to the production prompt changes the
hash and fails `tests/test_bench_freeze.py` — forcing a conscious, dated re-freeze and a
fresh test run. You cannot quietly tune the prompt against the test set.

**Scoring freeze.** The scorer has a version (`shared.metrics.SCORER_VERSION`) that must
equal the task's `meta.scorer_version`. Changing how grading works requires bumping both,
which invalidates prior held-out numbers.

---

## 6. Reporting rules

- **Report only held-out (`test`) results** as headline numbers. `dev`/`calibration`
  numbers may be shown but must be labelled as development metrics, never as the result.
- **Always report a confidence interval**, not a bare point estimate. With the small N we
  can hand-curate, the interval is wide on purpose — that honesty is the point.
- **Always report at least two baselines** alongside the model: a deterministic floor
  (e.g. the vocabulary baseline) and a majority-class baseline. A model is only
  interesting insofar as it beats the floor on held-out data.
- **Every reported number cites:** task, split, N, frozen-prompt hash, scorer version,
  model id, and date. A number without this provenance is not a result.

---

## 7. What would make us *remove* a benchmark

The same bar that deleted the previous one. Remove (don't quietly patch) a task if:
- a context-only or string-matching shortcut can score well (leakage), or
- its conclusions rest on a sample too small to support them and cannot be grown, or
- its ground truth cannot be defended.

Removal is reversible (git history); shipping an indefensible number is not.
