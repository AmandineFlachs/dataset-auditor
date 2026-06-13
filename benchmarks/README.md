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
labels_plausibility/     # the one shipped task
  meta.json  dev.jsonl  calibration.jsonl  test.jsonl
  baselines.py  run.py  PROMPT_FREEZE.md
triage_quality/          # Phase 5 scaffold only (not built)
```

## The one task: label-plausibility

Given an element and a claimed phase-at-STP, judge `plausible` / `implausible`. A
vocabulary check passes any value in `{solid, liquid, gas}`; only world knowledge catches
a planted defect (mercury labelled `solid`). It reuses the shipped
`auditor.checks.labels.build_label_prompt` + `LabelVerdict` so it can't drift from
production, and passes **no** `domain_context` (the leak vector).

Three disjoint splits (EVAL_PROTOCOL.md §4): `dev` (24, prompt iteration), `calibration`
(30, threshold tuning), `test` (40, **held-out, reporting only**). Classes are balanced
50/50; each element appears in exactly one split.

## Running locally (a local vLLM; no Kaggle, no auth)

```bash
# iterate on dev, then tune on calibration
python benchmarks/labels_plausibility/run.py --split dev          --model Qwen/Qwen3-4B
python benchmarks/labels_plausibility/run.py --split calibration  --model Qwen/Qwen3-4B

# FREEZE (already done): meta.json carries frozen_prompt.hash; PROMPT_FREEZE.md records it.
# final, held-out report (gated):
python benchmarks/labels_plausibility/run.py --split test --confirm-final --model Qwen/Qwen3-4B

# CI smoke (no model):
python benchmarks/labels_plausibility/run.py --split dev --mock
```

Each run writes a gitignored manifest to `labels_plausibility/results/` carrying the
metrics, both baselines, the frozen-prompt hash, and per-case predictions.

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

| Model | Inference path | Held-out accuracy (N=40) | 95% CI | Caught planted defects | Baselines |
| --- | --- | --- | --- | --- | --- |
| Qwen/Qwen3-4B | strict (forced JSON) | 0.500 | [0.352, 0.648] | 0 / 20 | vocab 0.500 · majority 0.500 |
| Qwen/Qwen3-4B | **reasoning** | **1.000** | [0.912, 1.000] | **20 / 20** | vocab 0.500 · majority 0.500 |

Same model, same frozen prompt, same held-out cases — the only change is letting the
reasoning model think before answering (`--reasoning`; see "reasoning mode" in
`src/auditor/llm.py`). The strict path forces `response_format=json_object`, which
suppresses the model's `<think>` step and makes it confabulate ("Helium is solid at STP");
reasoning mode drops that constraint and extracts the final JSON. This is why the shipped
`labels` check defaults to reasoning. The fix was driven by a diagnostic and the `dev`
split, never by inspecting `test`, so each row is a single honest held-out measurement.

## Before adding cases or a new task

Work through [`../docs/leakage_checklist.md`](../docs/leakage_checklist.md). The `[auto]`
items are enforced by `shared/leakage.py` + `assert_disjoint_splits` in CI; any hit fails
the build.
