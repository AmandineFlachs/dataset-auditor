# Next steps — dataset-auditor

_Updated 2026-06-14 (end of day). Active branch: **`v2`**. `main` = v1, untouched. Pick up at
next step #1 (test more models)._

> **Unpushed:** today's work (growth commit `5701e8a` + this doc update) is committed **locally
> only** — origin/`v2` is behind. `git push` when ready.

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
  Qwen3-4B: strict 0.500 → **reasoning 1.000 on BOTH domains**, beating the 0.500 baselines.
- **Held-out sets grown 40 → 80 per domain (2026-06-14).** Both now report **1.000, 95% CI
  [0.954, 1.000]** (was ~[0.912, 1.000] at N=40) — the CI tightening was the goal. The 40 new
  cases were authored via `benchmarks/_grow/grow.py` (metadata/ids/balance correct by
  construction; a disjointness-aware selector reads only existing ids, never test labels) and
  the chemistry ground truth was adversarially verified by a 3-lens workflow (clean, 0
  disputes). Re-run if needed: `python benchmarks/_grow/grow.py [--append]`.
- **Readiness rubric** (`auditor rubric` + report panel): deterministic per-dimension scores
  (meteorites 93, LeMat 98); LLM labels advisory-only.

Run a benchmark: `python benchmarks/run.py --task <labels_plausibility|element_classification>
--split <dev|calibration|test> --reasoning -m Qwen/Qwen3-4B` (held-out needs `--confirm-final`).
Needs the local vLLM up; if a call is slow, restart vLLM with a lower `--gpu-memory-utilization`
(VRAM paging) — that took a call from 149s to 8s.

## Next steps (in priority order)

1. **Test more models** (the still-open half of the old #1; growth to N=80 is done). One
   model isn't a comparison — run several so reasoning-mode's 1.000 is shown to generalise, not
   memorised. **Likely blocked by hardware**: only Qwen3-4B weights are local, 14B was abandoned
   on VRAM. Options: smaller models that fit the 3090 (e.g. Qwen3-1.7B/0.6B as a weaker
   contrast), or an API model as an upper bound. Decide the model set first.
   - _Optional further growth:_ a third domain, or push N past 80 (CI lower bound is 0.954 now;
     diminishing returns). Keep the discipline: balanced, disjoint, leakage-linted, author via
     `grow.py` so test labels are never inspected.
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
