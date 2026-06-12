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

## Running locally, no Kaggle (`local_run.py`)

`local_run.py` scores the same two tasks against a **local** LLM, with no `kbench` and no
Kaggle auth. It reuses the model-free `harness` and the shipped prompt builders, but sends
each case through the auditor's own `LLMClient` to a local vLLM endpoint. Same cases, same
prompts, same grading, so a model's local score previews its Kaggle score.

```bash
AUDITOR_LLM_MODEL=Qwen/Qwen3-4B python benchmarks/local_run.py            # both tasks
AUDITOR_LLM_MODEL=Qwen/Qwen3-4B python benchmarks/local_run.py --task verdict --timeout 180
```

### Findings so far (local Qwen3-4B)

- **labels-plausibility: 11/12.** Strong; the iconic `mercury-solid` passes. The one miss
  (`bromine-gas`) is a structured-output glitch — the model's *reason* is correct but it
  emitted the wrong boolean. (Use a generous `--timeout`; the Qwen3 reasoning model can
  exceed the 30s default and a timeout reads as a wrong answer.)
- **triage-verdict: 3/5, and it seesaws.** A flat binary prompt fails one way or the other
  depending on emphasis (over-calls "defect" or over-calls "expected"), reproducing the
  exact instability the shipped triage docstring records for the 14B. The 4B is **not**
  reliable enough to re-enable the verdict on a flat prompt.
- **A fix exists, partly landed.** The grounding half is now **done**: the `lemat_bulk`
  `domain_context` states DFT energies aren't comparable across functionals (the
  `energy-spread` case the sweep showed 4/5 proxy models miss). Still parked is the
  *structured domain-first* prompt (quote the governing domain sentence → classify the
  value's relation `conforms`/`violates`/`none` → map to verdict, with an `uncertain`
  abstention), which took the 4B to 4/5 stable and inspectable; its lone remaining miss is
  `dup-immutable-id`, whose governing sentence is compound. **Revisit the structured prompt
  after adding cases** — that is what would validate it beyond a 5-case sample before
  folding it into `VerdictResult` / `build_verdict_prompt`.

## Cross-model sweep, run locally (`proxy_sweep.py`)

`proxy_sweep.py` runs both tasks against **every model the Kaggle model proxy exposes**,
without the server-side import wall. It accesses each model via `kbench.llms[<name>]`,
which runs the task code (and so `auditor` + `harness`) on *this* machine and sends only
inference to the proxy. Same cases, same shipped prompts, same grading as the task files
and `local_run.py` — just swept across the proxy roster read from `.env`'s `LLMS_AVAILABLE`.

```bash
kaggle b init -y                                       # refresh .env proxy creds (~hourly)
PYTHONIOENCODING=utf-8 python benchmarks/proxy_sweep.py
```

### Scoreboard (2026-06-12, after two case/grounding fixes)

| model | labels | triage-verdict | overall |
|---|---|---|---|
| claude-haiku-4-5 | 12/12 | 5/5 | **17/17** |
| deepseek-v3.2 | 12/12 | 5/5 | **17/17** |
| gemini-3-flash | 12/12 | 5/5 | **17/17** |
| gemini-3.1-flash-lite | 12/12 | 5/5 | **17/17** |
| qwen3-next-80b | 12/12 | 5/5 | **17/17** |
| glm-5 | 12/12 | 5/5 | **17/17** |
| gpt-oss-120b | 7/12 | 5/5 | 12/17 \* |

\* gpt-oss-120b's misses are all **structured-output** failures on labels (it cannot reliably
emit the schema; the count varies run-to-run, 7–9/12), not judgment errors — a
format-compliance signal, not a reasoning one. Its verdict score is a clean 5/5.

What the sweep taught us:

- **The withheld verdict is reliably doable — re-enable it, gated on a capable model.** Every
  capable model scores **5/5 on triage-verdict using the shipped flat prompt**, no structural
  change. The local 4B's seesaw is a capability floor, not a task flaw. This is the concrete
  evidence to reintroduce the verdict feature that `triage.py` currently withholds.
- **It localized one grounding gap to a single sentence (now fixed).** Pre-fix, five models
  missed `energy-spread` for a defensible reason: the old `domain_context` said computed
  properties "should be physically consistent", and they followed it. `lemat_bulk.domain_context`
  now states pbe/pbesol/scan use different energy references, so an energy spread across rows
  sharing an `immutable_id` is expected physics. Post-fix, **all seven models call it correctly.**
- **It caught a mislabeled benchmark case — the sweep's best moment.** Three capable models
  scored the *old* `formula-mismatch` case "wrong" with identical, correct chemistry: its
  sample `descriptive=Cd2In2P2 / reduced=CdInP` is a **valid GCD reduction** (both are 1:1:1),
  not a contradiction — and the real `formula.check` reduces both columns before comparing, so
  it would *not* fire on that row. The ground truth was wrong; the models were right. The case
  now uses a genuine contradiction (`reduced=Cd2InP`, i.e. 2:1:1 vs the descriptive's 1:1:1),
  which the real check *does* flag. When several capable models agree against the label for the
  same sound reason, suspect the label — that is exactly what a cross-model sweep is for.

Honest caveat: this is **17 assertions** (12 + 5), and with both fixes in the verdict task now
**saturates** for capable models (all 5/5) — good evidence for the re-enable decision, but it
no longer *ranks* capable models. To recover discriminating power, the verdict set needs
genuinely harder cases (the prior "discrimination" was partly the bad case penalizing correct
chemistry). The design stays drift-proof (it runs the shipped builders); the case set is what
needs to grow.

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
