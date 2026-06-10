# Benchmarks — evaluating the auditor's model-judgment layer

The report is for humans; **these benchmarks are for comparing model behavior on the
auditor's ambiguous, model-judged decisions.** The deterministic checks are facts and
are covered by `pytest`; this directory measures the only fallible part — the LLM
judgments — as [Kaggle Community Benchmarks](https://www.kaggle.com/benchmarks).

Two tasks (Phase 1, deliberately small):

| Task | File | What it measures | Ground truth |
| --- | --- | --- | --- |
| `labels-plausibility` | `labels_plausibility.py` | Can a model tell a labelled phase-at-STP is wrong (mercury labelled `solid`)? Reuses the **shipped** `labels.build_label_prompt`. | `cases/elements/labels.jsonl` |
| `triage-verdict` | `triage_verdict.py` | Can a model judge real-defect vs expected-artifact — the verdict the shipped triage **withholds** because a 14B got it wrong? | `cases/lemat_bulk/triage_verdict.jsonl` |

The decisive payoff of `triage-verdict`: if a model reliably calls the ~122
cross-functional duplicate ids an *expected artifact* (and the formula/range issues
*real defects*), that is the evidence to **re-enable the verdict feature** that was
removed from `triage.py`.

## How it is wired

- The tasks call the auditor's **real** prompt builders (`build_label_prompt`,
  `build_verdict_prompt`) and output schemas (`LabelVerdict`, `VerdictResult`), so the
  benchmark can never drift from what ships.
- `harness.py` is pure (no kbench, no httpx): it loads the `cases/<name>/` fixtures and
  grades a parsed model answer against the golden label. It is unit-tested in
  `tests/test_benchmark_harness.py`, so CI needs no live model and no Kaggle SDK.
- Domain grounding is read from the real `DatasetSpec.domain_context` where one exists
  (`lemat_bulk`); the fixture-only `elements` benchmark carries its own in `meta.json`.

## Running

Install the extra: `pip install -e ".[bench]"` (adds `kaggle-benchmarks` + `kaggle`).

```bash
kaggle b init -y                                  # writes .env with model-proxy creds

# 1. Validate locally — runs the task on your machine, calling the proxy for the model.
python benchmarks/labels_plausibility.py          # produces a .run.json
python benchmarks/triage_verdict.py

# 2. Push, then run across models (free within quota). Include open-weight models
#    (Llama/DeepSeek/...) so the ranking pre-screens Phase 2 local candidates.
kaggle b t push labels-plausibility -f benchmarks/labels_plausibility.py --wait
kaggle b t run  labels-plausibility -m <model-a> -m <model-b>     # repeat -m, never "-m a b"
kaggle b t download labels-plausibility -o ./results

# 3. Build the model x task scoreboard from the downloaded runs.
python benchmarks/compare.py ./results                            # print the table
python benchmarks/compare.py ./results -o results/scoreboard.md   # ...or write it
```

Gotchas (from the `write-kaggle-benchmarks` skill): a missing module-level `.run()` is a
silent no-op; re-pushing without `-d` detaches attached datasets; the task slug must
match the `@kbench.task(name=...)`.

### Reading the results

Each case is one `assert_equal`, so a task's score is the fraction of cases the model
judged correctly. `compare.py` reads the downloaded `*.run.json` files and prints a
`model × task → score` Markdown table (best Overall first); a model that tops both tasks
is best placed to advise on a given dataset's triage. It is stdlib-only and scores from
each run's assertion pass-rate; if a run carries no model id (e.g. a local stub run) it
falls back to the file stem, so naming downloads `<task>.<model>.run.json` keeps the
table tidy.

## Open questions to confirm (per the plan)

- **Which models the proxy exposes**, and whether open-weight models are included — this
  sets how well Phase 1 pre-screens Phase 2 local candidates. Check `kaggle b t run` help.
- **Server-side `kaggle b t run`** executes the task on Kaggle's side, where `auditor`
  and `harness` are not installed. Local `python task.py` validation works (this repo is
  importable via the `sys.path` bootstrap at the top of each task). For server runs,
  attach the repo as a dataset (`-d`) and extend the path, or keep runs local. Confirm
  before relying on the push/run path.
- **Case count.** Trust scales with it; with a handful of cases the ranking is honestly
  *advisory*. If strong and weak models score the same, add cases.

## Phase 2 (deferred)

Generalize to **locally-run open-source models**: reuse these same tasks, fixtures, and
grading, but point execution at a local vLLM via `auditor.llm`, and turn the ranking into
a "which local model should I run for this dataset's triage" recommendation (with VRAM
filtering). Phase 1's open-weight ranking narrows the candidates first.
