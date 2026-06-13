# Next steps — dataset-auditor

_Updated 2026-06-13 (end of day). Active branch: **`v2`** (pushed to origin). `main` = v1,
untouched. Pick up here tomorrow._

## Where things stand (v2 branch)

The leakage-safe evaluation layer + readiness rubric are built and held-out-verified.
**219 tests pass.**

- **Evaluation protocol** locked first: `EVAL_PROTOCOL.md`, `docs/methodology.md`,
  `docs/leakage_checklist.md`.
- **Two leakage-safe benchmark tasks** (`benchmarks/`, local-only, no Kaggle): reuse the
  shipped `build_label_prompt`/`LabelVerdict`, pass no answer-bearing context, disjoint
  dev/calibration/hidden splits, frozen prompt, automated leakage linter, value↔label
  decorrelation guard — all enforced by `tests/test_bench_tasks.py`.
  - `labels_plausibility` (phase-at-STP) and `element_classification` (metal/nonmetal/metalloid).
- **Reasoning mode** (`auditor.llm`, opt-in; default-on for the `labels` check). Held-out on
  Qwen3-4B: strict 0.500 → **reasoning 1.000 (40/40) on BOTH domains**, beating the 0.500
  baselines.
- **Readiness rubric** (`auditor rubric` + report panel): deterministic per-dimension scores
  (meteorites 93, LeMat 98); LLM labels advisory-only.

Run a benchmark: `python benchmarks/run.py --task <labels_plausibility|element_classification>
--split <dev|calibration|test> --reasoning -m Qwen/Qwen3-4B` (held-out needs `--confirm-final`).
Needs the local vLLM up; if a call is slow, restart vLLM with a lower `--gpu-memory-utilization`
(VRAM paging) — that took a call from 149s to 8s.

## Next steps (in priority order)

1. **Grow the case set further + test more models.** Each held-out set is N=40 (CI ~±9pp at
   100%). Add more cases (and/or a third domain) to tighten it, and run several models so the
   result becomes a real comparison, not one model. Highest value, lowest risk. Keep the
   discipline: balanced, disjoint, leakage-linted, don't open `test` while authoring.
2. **Phase 5: a second *kind* of task** (e.g. brief-grounding) — only after #1. "Usefulness"
   isn't a clean binary, so it needs an LLM-as-judge grader with its own leakage controls +
   human spot-check. Scaffold lives at `benchmarks/triage_quality/`.
3. **Decide reasoning for `brief`/`triage`** — measure it (via #2), don't guess.
4. **Publish to Kaggle** — distribution step, gated behind #1 (grown + multi-model). Work:
   solve the server-side import wall (vendor `shared/` into the task or attach repo as dataset),
   carry over the leakage discipline, re-add the `kaggle` dev extra.
5. **Ship decision** — when v2 is ready: PR `v2 → main`, tag `v0.2.0`, CHANGELOG, fold the v2
   sections into README/ROADMAP as the current version.

## Small items
- `.env` (stale Kaggle key) is gitignored but still on disk — Amandine chose to keep it.
- `demo/` is untracked throwaway.
- The `labels` check defaults to reasoning but both shipped datasets leave `label_rules` empty,
  so it's demonstration-only until a dataset with human-entered categoricals is added.

## Operational notes
- Commit email stays `AmandineFlachs@users.noreply.github.com`.
- Run from repo root with `PYTHONPATH=src` (package isn't installed); tests need `src` + `benchmarks` on the path (pyproject sets this).
- Explainer HTML lives OUTSIDE the repo at `../project-explainer.html` (kept off GitHub on purpose); it has a "Benchmark & rubric" page reflecting this work.
