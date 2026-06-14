# Next steps — dataset-auditor

_Updated 2026-06-14. Active branch: **`v2`**. `main` = v1, untouched. **Decision locked: ship +
publish what's proven; defer more eval depth** (see Deferred). Pick up at step #1 (ship `v0.2.0`),
then step #2 (publish to Kaggle — the part to dive into next)._

> **Unpushed:** v2 is ahead of origin and has uncommitted doc edits (the `v0.2.0` README / ROADMAP
> / CHANGELOG rewrite). Commit + `git push` v2, then do the ship steps below.

## Where things stand (v2 branch)

The leakage-safe evaluation layer + readiness rubric are built and held-out-verified.
**223 tests pass.**

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
  (meteorites 94, LeMat 99); LLM labels advisory-only.
- **Second model tried — Qwen3.5-0.8B (2026-06-14): below the protocol floor.** It cannot
  complete either held-out benchmark under the frozen prompt — it echoes the verbose pydantic
  schema back instead of instantiating it (deterministic at `temperature=0`, so retries don't
  help; same failure in reasoning and strict mode). A side-probe with a *flattened* schema shows
  it knows the chemistry (Iron→solid, conf 0.99), so this is schema-in-prompt brittleness, not
  ignorance. We did **not** flatten the prompt to rescue a score — that would be tuning the
  frozen prompt on the held-out set and would break comparability with the 4B. So the honest
  multi-model result: **4B reasoning 1.000 on both domains; 0.8B non-compliant (no score).**
  The 1.000 is not trivially reproducible by any model, and the `judge()` contract is brittle
  for very small models (see robustness item below).

Run a benchmark: `python benchmarks/run.py --task <labels_plausibility|element_classification>
--split <dev|calibration|test> --reasoning -m Qwen/Qwen3-4B` (held-out needs `--confirm-final`).
Needs the local vLLM up; if a call is slow, restart vLLM with a lower `--gpu-memory-utilization`
(VRAM paging) — that took a call from 149s to 8s.

## Next steps (in priority order)

1. **Ship `v0.2.0`.** The doc rewrite is **done** (README version + Evaluation table, ROADMAP v2
   section + deferred list, CHANGELOG `[0.2.0]`, and the external explainer's benchmark page).
   Remaining, in order: commit the doc edits → `git push` v2 → open PR `v2 → main` → merge →
   tag `v0.2.0` + push tag. (Optional cleanup: delete the stale `origin/v2-kaggle-benchmarks`.)
2. **Publish the proven benchmark to Kaggle — the part to dive into next.** Decisions to make
   *before* anything goes public:
   - **How to publish without burning the held-out test.** A held-out set is only meaningful
     while its answers are secret. A **Kaggle Community Benchmark** keeps the answer key
     server-side and scores submissions (preferred); a plain **Dataset** would expose the test
     and void future held-out use. Pick the format first — it drives everything else.
   - **The server-side import wall.** Kaggle's runner can't `import shared`. Either vendor
     `benchmarks/shared/` into the task notebook or attach the repo as a dataset.
   - **Carry the discipline over:** frozen prompt + hash, baselines, no answer-bearing context,
     the leakage linter. Re-add the `kaggle` dev extra (removed earlier).
   - **Scope:** publish both proven tasks (`labels_plausibility`, `element_classification`).
     Decide license/attribution (code is MIT).

## Deferred — decided gold-plating (2026-06-14)

The core claim (advisory LLM label check is trustworthy) is already defended. These wait until
there's a concrete reason to reopen them — don't pursue without a fresh ask:
- **More models.** Low marginal value: memorization is defended structurally, not by multi-model
  runs, and the 0.8B "can't comply" contrast already exists. (A clean *scoring* contrast would
  want a mid-tier model that complies but scores imperfectly — hardware-gated.)
- **A second *kind* of task.** Calibration would validate the `confidence` field, but that field
  is advisory-only in the product, so it hardens no claim a reviewer is asking about. The
  LLM-as-judge variant imports a model-grading-model trust dependency. Scaffold stays at
  `benchmarks/triage_quality/`.
- **Further case growth** (third domain / N>80): diminishing returns; CI lower bound is 0.954.

## Small items
- **`judge()` schema-in-prompt is brittle for tiny models** (found 2026-06-14 with 0.8B).
  `_build_messages` injects the full `model_json_schema()` (nested `description`/`title`); very
  small models parrot it instead of instantiating. A flattened/example-based schema would harden
  the contract. NB: changing it bumps the frozen prompt hash, so it's a *protocol v-next*
  re-freeze + re-run-both-models task, not a quiet edit. Doesn't affect the 4B results.
- `.env` (stale Kaggle key) is gitignored but still on disk — Amandine chose to keep it.
- `demo/` is untracked throwaway.
- The `labels` check defaults to reasoning but both shipped datasets leave `label_rules` empty,
  so it's demonstration-only until a dataset with human-entered categoricals is added.

## Operational notes
- Commit email stays `AmandineFlachs@users.noreply.github.com`.
- Run from repo root with `PYTHONPATH=src` (package isn't installed); tests need `src` + `benchmarks` on the path (pyproject sets this).
- Explainer HTML lives OUTSIDE the repo at `../project-explainer.html` (kept off GitHub on purpose); it has a "Benchmark & rubric" page reflecting this work.
