# Benchmarks — measuring the advisory LLM, leakage-safe

The deterministic checks are facts and are covered by `pytest`. This directory measures the
**only fallible part — the LLM's judgement** — under the rules in
[`../EVAL_PROTOCOL.md`](../EVAL_PROTOCOL.md). The design exists to make one failure
impossible: a benchmark whose context hands the model the answer (see
[`../docs/methodology.md`](../docs/methodology.md) for the story).

## Layout

```
shared/                  # PURE, model-free (no httpx, no model SDK) — unit-tested in CI
  cases.py               # load splits + assert_disjoint_splits
  grader.py              # case -> SHIPPED build_label_prompt; grade a LabelVerdict
  metrics.py             # accuracy / P,R,F1 / Wilson CI / score_split (versioned)
  leakage.py             # leakage_check(cases, meta) — the automated checklist
  freeze.py              # prompt-identity hash, verify_frozen_prompt, run manifest
  baselines.py           # vocabulary-floor + majority-class (task-agnostic)
run.py                   # the one IMPURE file: --task <dir> --split <dev|calibration|test>
labels_plausibility/     # task 1: phase-at-STP
  meta.json  dev.jsonl  calibration.jsonl  test.jsonl  PROMPT_FREEZE.md
element_classification/  # task 2: metal / nonmetal / metalloid
  meta.json  dev.jsonl  calibration.jsonl  test.jsonl  PROMPT_FREEZE.md
```

## The two tasks

Both ask the same shape of question — given an element + a claimed categorical value (plus
answer-free context: element/symbol/atomic_number/period), is it `plausible` or
`implausible`? Both reuse the shipped `build_label_prompt` + `LabelVerdict` and pass **no**
`domain_context`. Each has three disjoint splits (`dev` 24 / `calibration` 30 / `test` 40,
classes balanced 50/50, each element in one split), and every value appears in both classes
so there is no "guess by the word" shortcut.

- **`labels_plausibility`** — phase-at-STP (mercury labelled `solid` is the iconic defect).
- **`element_classification`** — metal / nonmetal / metalloid (oxygen labelled `metal`).
  Added as a second domain because phase-at-STP is naturally capped (only 13 non-solid
  elements exist); a second domain tests *generalization*, not just phase recall.

## Running locally (a local vLLM; no Kaggle, no auth)

```bash
# iterate on dev, then tune on calibration (use --reasoning for reasoning models like Qwen3)
python benchmarks/run.py --task element_classification --split dev --reasoning --model Qwen/Qwen3-4B

# FREEZE (already done): each task's meta.json carries frozen_prompt.hash; PROMPT_FREEZE.md records it.
# final, held-out report (gated):
python benchmarks/run.py --task element_classification --split test --confirm-final --reasoning --model Qwen/Qwen3-4B

# CI smoke (no model):
python benchmarks/run.py --task labels_plausibility --split dev --mock
```

Each run writes a gitignored manifest to `<task>/results/` carrying the metrics, both
baselines, the frozen-prompt hash, and per-case predictions.

## Reporting rules (enforced by the protocol)

Report only the **held-out** (`test`) number, always with its 95% confidence interval and
**both baselines** (vocabulary-floor + majority-class), citing task/split/N/frozen-prompt
hash/scorer version/model/date. With N=40 the interval is wide (~±15pp) — that honesty is
the point. The model is only interesting if it clearly beats both baselines on held-out
data. To narrow the interval, grow the `test` split (more curated cases), never by tuning
on it.

## Results

Held-out (`test`) results, reported per EVAL_PROTOCOL.md §6 (one-shot, with a 95% CI and
both baselines). Provenance: frozen prompt `sha256:03bab39d…`, scorer `1.0.0`, 2026-06-13.

| Task | Model | Inference path | Held-out (N=40) | 95% CI | Caught planted defects |
| --- | --- | --- | --- | --- | --- |
| labels_plausibility | Qwen/Qwen3-4B | strict (forced JSON) | 0.500 | [0.352, 0.648] | 0 / 20 |
| labels_plausibility | Qwen/Qwen3-4B | **reasoning** | **1.000** | [0.912, 1.000] | **20 / 20** |
| element_classification | Qwen/Qwen3-4B | **reasoning** | **1.000** | [0.912, 1.000] | **20 / 20** |

Baselines on every row: vocabulary-floor 0.500, majority-class 0.500. Provenance per task in
its `meta.json` (`frozen_prompt.hash`, `scorer_version`); runs dated 2026-06-13.

Same model, same frozen prompt, same held-out cases — the only change between the first two
rows is letting the reasoning model think before answering (`--reasoning`; see "reasoning
mode" in `src/auditor/llm.py`). The strict path forces `response_format=json_object`, which
suppresses the model's `<think>` step and makes it confabulate ("Helium is solid at STP");
reasoning mode drops that constraint and extracts the final JSON. This is why the shipped
`labels` check defaults to reasoning. The second domain (`element_classification`) confirms
the win generalizes beyond phase recall. Every fix was driven by diagnostics and the `dev`
split, never by inspecting `test`, so each row is a single honest held-out measurement.
(`element_classification` strict was not run; the json_object suppression is model-/path-level,
so a similar floor is expected, but it is not claimed here since it was not measured.)

## Before adding cases or a new task

Work through [`../docs/leakage_checklist.md`](../docs/leakage_checklist.md). The `[auto]`
items are enforced by `shared/leakage.py` + `assert_disjoint_splits` in CI; any hit fails
the build.
