# Next steps — dataset-auditor

_Updated 2026-06-15. Active branch: **`v2`**. `main` = v1, untouched. `v0.2.0` is shipped, and the
benchmark is now **published on Kaggle** (4 tasks, open + fresh-private, public cross-model
leaderboard). Pick up at step #1 (commit the `kaggle/` work)._

> **Pushed:** the `kaggle/` work + docs are committed and on `origin/v2` (commit `4fe0720`). The
> fresh-private set, its generator, `.env`, and `*.task.json`/run artifacts stay gitignored. Only
> this next-steps refresh is uncommitted. The four leaderboards are **public** on Kaggle.

## DO THIS FIRST (2026-06-17+): fill the cross-model board in one paced pass

Today (2026-06-16) we hit a **hard daily-credit wall**: uncapped `reasoning="high"` calls reserve
~$0.31-0.42 EACH (full context window), and the day's free credit dropped below a single call's
reservation, so every heavy model (Haiku on 3/4, both qwen, glm-5) 403'd. Lowering concurrency does
NOT help — the binding limit is per-call reservation vs available quota, not peak parallelism. A cap
does not help either: `reasoning="high"` sets a server-side thinking budget >24576, so any cap that
shrinks the reservation also makes Anthropic models 400 and truncates thinking models (null
response). So the tasks are **uncapped** (the validated config) and the only missing ingredient is
credit, which returns at the reset. Nothing needs re-pushing — the four tasks are on their final
config (uncapped, `max_workers=2`).

When credit has reset:
1. **Re-auth** (OAuth lapses overnight): `! ../.kaggle-scratch-venv/Scripts/kaggle.exe auth login`.
2. **Run** `bash kaggle/private/fill_board.sh` — refreshes the proxy key, then a PACED,
   headline-first sweep (one model across the four tasks per batch, waiting for each to settle so
   reservations stay small), retries the transient (429/503) models once, and prints the final board
   via `kaggle/private/_parse_lb_full.py`. ~30-60 min, unattended. (Both scripts are gitignored.)
3. **Refresh tables** in `README.md` + `../project-explainer.html` from the printed board.

Caveats: gpt-oss-120b (503) and deepseek-v3.2 (429) have been down on transient provider errors all
day — those cells may stay empty (not our bug). If reservations still 403 at full morning credit,
the reset cadence is longer than daily — wait accordingly. Re-pushing resets the version-scoped
leaderboard, so do NOT push unless the task code itself changes.

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

## Done since last update (2026-06-15)

- **`v0.2.0` shipped** (merged to `main`, tagged).
- **Benchmark published to Kaggle** — 4 tasks (`labels-plausibility` + `element-classification`,
  each *open* and *fresh-private*), public cross-model leaderboard. Built with
  `kaggle/build_open_tasks.py` (open) + `kaggle/private/build_private_tasks.py` (private,
  gitignored), validated locally via `kaggle/run_local.py` + `kaggle/local_adapter.py`. See
  [`kaggle/README.md`](../kaggle/README.md). Key findings: Claude Haiku 4.5 = 1.000 across all
  four; Qwen3-Next-80B **Thinking 1.000 vs Instruct 0.513** on phase (reasoning thesis, live);
  private tracks open (no contamination inflation). DeepSeek V3.2 unavailable via proxy; Qwen
  Thinking completed 1/4 (long-reasoning calls exceeded the proxy per-call limit).

## Plan for tomorrow — fill out the leaderboard

The current board has gaps, but they are **error-type, not quota-type**: DeepSeek V3.2 erred on
*every* attempt (including the first batch, before heavy use) → model/proxy-specific, not
throttling; Qwen-Thinking finished 1/4 because a few long-reasoning calls exceeded the proxy's
*per-call* limit. The "1 hour" we hit was the Model Proxy **key TTL** (refresh with
`kaggle benchmarks init`), not a daily cap. So a reset alone won't fill the gaps — these steps will.

Setup each session: scratch venv at `../.kaggle-scratch-venv`, `PYTHONUTF8=1`, refresh creds with
`kaggle benchmarks init -y` (writes `.env`, ~1h TTL). Run via `../.kaggle-scratch-venv/Scripts/kaggle.exe`.

1. **Diagnose DeepSeek, then one retry.** Pull its kernel log
   (`kaggle kernels list --mine` → `kaggle kernels output <slug> -o kaggle/private/_dbg`) to learn
   *why* it errors. If transient, one `run -m deepseek-v3.2` may fix it; if the model is genuinely
   unavailable via the proxy, drop it and note so.
2. **Add 2–3 reliably-completing frontier models** to all four tasks — `claude-opus-4-8-default`,
   `gpt-5.5-2026-04-23`, `gemini-3.5-flash`, `claude-sonnet-4-6-default` are in the catalog and
   should just work. This is the real win for a fuller board. Re-pull results with
   `kaggle/private/_parse_lb.py` and refresh the tables in README + explainer.
3. **(Decide deliberately) Per-case failure tolerance** so thinking-style models finish: catch a
   timed-out case in `_score_all` (skip or retry), report the *effective* N + the exclusions. This
   is a methodology change — defensible only if stated openly. Touches the RUNTIME template in
   `kaggle/build_open_tasks.py`, then regenerate + re-push all four.

Reminder: any re-push regenerates from `kaggle/build_open_tasks.py` (open) /
`kaggle/private/build_private_tasks.py` (private). Keep descriptions <255 chars (the validation
gotcha). Private tasks always publish with `--no-publish-backing-notebook`.

## Later / optional
- **Community/visibility.** The four leaderboards are public — link them anywhere the project is
  showcased.

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
