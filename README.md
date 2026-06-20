# dataset-auditor

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Local &amp; free](https://img.shields.io/badge/runs-fully%20local%20%C2%B7%20no%20paid%20API-brightgreen.svg)

Point heuristics + a *local* LLM at a public scientific dataset and get a clean,
**self-contained HTML report** flagging PII, unit/format inconsistencies, label
noise, and duplicates. Fully local, free, no paid API.

The auditor is **multi-dataset**: per-dataset knowledge lives in a small config
registry, so the check *engines* stay generic. The flagship is
**[LeMaterial/LeMat-Bulk][lemat]** (DFT materials properties harmonized from Materials
Project + OQMD + Alexandria); **NASA Meteorite Landings** is the proving ground.

> Early but functional — `v0.2.0`. Built in public.

📖 **[Read the project explainer →](https://amandineflachs.github.io/dataset-auditor/)** — the full
story: what it does, the leakage-safe benchmark, and the cross-model leaderboard.

### What it does

- 🔍 **Eight deterministic checks** — missing data, impossible / out-of-range values,
  duplicate rows and keys, near-duplicates, cross-field consistency, PII, categorical
  label plausibility, and chemical-formula agreement.
- 🧭 **Found → Expected** on every finding with a concrete target (a range, uniqueness,
  the canonical formula); an honest Evidence → Fix fallback where there is no single
  right answer.
- 🤖 **Advisory local LLM** (vLLM) for research briefings, triage notes, and label
  judgement — it *never* changes a deterministic finding (see [below](#deterministic-vs-the-llm)).
- 📊 **Self-contained HTML triage report** — category rail, severity summary, expandable
  issues, in-browser keep / dismiss / needs-review, CSV export. No external resources.
- 🧩 **Multi-dataset by design** — onboard a dataset by adding one `DatasetSpec`, not new
  check code.

### How it works

One generic engine runs every check; per-dataset knowledge is just data in a registry.
The **deterministic core always runs and produces the facts**; the local LLM is an optional
side-channel that can *annotate and orient* but **never overrides a finding**.

```mermaid
%%{init: {'flowchart': {'curve': 'linear'}}}%%
flowchart TD
    DS["Dataset / CSV"] --> LD["load — normalize schema, dtypes, stable row_id"]
    LD --> DET["Deterministic checks — always on<br/>schema · units · duplicates · near-dup<br/>consistency · PII · formula"]
    LD -. optional, advisory .-> LLM["Local LLM<br/>label plausibility · briefing · triage notes"]
    DET ==> FN["Findings — one shared schema"]
    LLM -. never overrides .-> FN
    FN --> RP["Self-contained HTML report"]
    FN --> RB["Readiness rubric"]
    FN --> TR["Triage priority"]
```

The report is a single self-contained HTML file — a triage dashboard with a health
summary, a per-check category rail, and expandable findings:

![The audit report overview: health summary, category rail, and grouped findings](docs/images/report-overview.png)

Every finding expands to show the evidence, a **Found → Expected** comparison, the
record context, and in-browser keep / dismiss / needs-review controls:

![An expanded finding showing the Found vs Expected comparison and triage controls](docs/images/report-detail.png)

See the full sample audit in **[`examples/`](examples/)** (open `lemat_bulk_report.html`
in a browser).

[lemat]: https://huggingface.co/datasets/LeMaterial/LeMat-Bulk

## Quickstart

```powershell
git clone https://github.com/AmandineFlachs/dataset-auditor.git
cd dataset-auditor
uv pip install -e ".[cli,report,load]"   # CLI + HTML report + loader deps
python scripts/acquire_meteorites.py     # fetch the demo dataset (data/ is git-ignored)
auditor run --dataset meteorites --out report.html --open
```

`data/` is git-ignored, so the datasets are fetched by small acquire scripts rather than
committed: `acquire_meteorites.py` for the proving ground above, and `acquire_lemat.py`
for the flagship LeMat-Bulk sample (see [Datasets](#datasets)).

`auditor run` audits a dataset and writes a single self-contained HTML report — a
**triage view**: a category rail, a summary strip leading with count and severity
plus the clean-rate, and a grouped, expandable issue stream. Identical findings are
aggregated; each issue expands to show evidence, the suggested fix, and the source
record, and can be marked keep / dismiss / needs-review (saved in the browser, and
exportable to CSV). The layout was built from a Claude Design handoff; it stays fully
self-contained (system fonts, no external resources). Other commands:

```powershell
auditor datasets                          # list available datasets
auditor run -d meteorites -s my.csv       # audit any CSV with a chosen spec
auditor profile -d meteorites             # exploratory profile (no findings)
auditor rubric -d meteorites              # dataset-readiness scores per dimension
auditor brief -d lemat_bulk -o brief.md   # local-LLM domain briefing (needs a server)
auditor triage -d lemat_bulk              # prioritize findings; LLM adds notes (needs a server)
```

`auditor rubric` rolls the deterministic findings up into a **dataset-readiness** score
per dimension (completeness, consistency, plausibility, duplication, privacy) plus an
overall number — a first step toward "is this dataset fit for use?", not just "what's
wrong?". It is a deterministic aggregation of facts: LLM-judged labels are advisory only
and never move a score, and a dimension whose checks didn't run shows `n/a` rather than a
misleading 100. The same panel appears at the top of the HTML report.

`auditor triage` collapses the findings into distinct issues and orders them by a
**deterministic** priority (severity, then affected rows); a local LLM adds a plain
summary and a "what to check" line per issue. The priority never depends on the model,
and the order still prints if no server is running. The model is deliberately *not*
asked to judge real-defect-vs-expected, the most error-prone call in the pipeline: a
model can confidently call the expected cross-functional duplicate ids a defect to "remove",
so triage is scoped to what the model is reliable at — orientation and suggesting what to verify.

Sample reports for both flagships live in [`examples/`](examples/), alongside the
live local-LLM research briefings (`*_briefing.md`) from `auditor brief` and the
triage (`lemat_bulk_triage.md`) from `auditor triage`. The LeMat-Bulk report is the
genuine audit of the real sample **plus five deliberately-planted `formula.*` defects**
— the real data is clean on that axis, so the planting is what lets the example *show*
the formula check firing. It is planted in memory only (the data is untouched) and
fully reproducible: `python scripts/make_example_report.py`, which lists exactly what
it corrupts.

## Design in one sentence

Every check returns a list of `Finding` objects with the same schema, so the
report layer is generic. Add a new check → the report renders it for free.

## Deterministic vs. the LLM

Everything the report asserts as a fact is **deterministic**. Unplug the local LLM
and the audit is unchanged: every error- and warning-level finding (out-of-range
values, duplicates, near-duplicates, missing data, formula disagreements, cross-field
inconsistencies) comes from plain Python with no model in the loop. The evidence, the
severity, and the Found → Expected target are all computed, not generated.

The local LLM is **advisory only**, in three clearly-bounded places, and it never
overrides a deterministic finding:

| Where | What the LLM does | If the server is off |
|---|---|---|
| `auditor brief` | Writes a research briefing (column meanings, plausible ranges, pitfalls, *suggested* checks) from column **metadata only — never raw rows**. A separate command, not part of `run`. | The briefing is skipped; the audit is unaffected. |
| `auditor triage` | Ranking is **deterministic** (severity, then affected rows). The model only adds a plain summary and a "what to check" line per issue. | The priority order still prints, without the notes. |
| `checks/labels.py` | The one check that asks the model to judge whether a categorical value is plausible given the row. Its findings are **warn/info** ("a human confirms"), it samples rather than scans, and both flagships leave it disabled. | One `info` finding ("skipped"); every other check runs untouched. |

So the LLM can *originate* a finding in exactly one opt-in place (`labels.py`), and
only at advisory severity — it is never allowed to assert a hard error, and it cannot
change, suppress, or re-rank a deterministic one. The audit you can defend in front of
a scientist is the deterministic core; the LLM is there to orient and explain, and it
is held to that on purpose (a local model can confidently mis-judge an *expected* cross-functional
duplicate as a defect, which is exactly why triage does not let it render verdicts).

## Architecture

```
src/auditor/
├── models.py     # Finding, Severity: the shared data contract
├── datasets.py   # DatasetSpec registry: all per-dataset knowledge as data
├── load.py       # dataset/CSV -> normalized pandas DataFrame
├── llm.py        # thin client for the local LLM (vLLM, OpenAI-compatible)
├── checks/       # schema, units, duplicates, consistency, near_dup, pii, labels,
│                 #   formula: each -> list[Finding]
├── glossary.py   # plain-language names + severity words for the report
├── research.py   # `auditor brief`: metadata-only LLM research briefing
├── triage.py     # `auditor triage`: deterministic priority + advisory LLM notes
├── report.py     # Jinja2 -> a single self-contained report.html
└── cli.py        # the `auditor` CLI: run / datasets / profile / brief / triage
templates/
└── report.html.j2  # the Triage report template (inline CSS + JS, self-contained)
```

## Datasets

A `DatasetSpec` (`auditor/datasets.py`) collects everything dataset-specific
(rename map, numeric columns, unique key, plausibility rules) as **data**, so the
check *engines* stay generic. Onboarding a dataset is: add one spec, author its
rules. The checks don't change.

```powershell
auditor run                          # default: LeMat-Bulk (flagship)
auditor run --dataset meteorites     # the proving ground
```

`data/` is git-ignored, so each dataset is fetched by a small acquire script:

```powershell
python scripts/acquire_meteorites.py   # the proving ground (~45k rows, public mirror)
python scripts/acquire_lemat.py        # the flagship sample, across all four configs
```

The LeMat-Bulk script draws a reproducible random sample of the scalar science columns
across all four configs (`compatible_pbe/pbesol/scan`, `non_compatible`).

## Roadmap

Everything through **`v0.2.0` is ✅ done** — the `v0.1.0` core (checks, report, live local-LLM
runs against a real vLLM server) plus the v2 leakage-safe evaluation layer and readiness rubric.
The benchmark is now **published on Kaggle** as a public, cross-model leaderboard (see
[`kaggle/`](kaggle/) and [Evaluation](#evaluation)).

| Phase | What | Status |
|---|---|---|
| 0 | Scaffold + `Finding` contract | ✅ Done |
| 1 | Load + profile a dataset (meteorites, the origin) | ✅ Done |
| 2 | Deterministic checks (schema / units / exact dups) | ✅ Done |
| 2.5 | Generalize to multi-dataset + adopt **LeMat-Bulk** flagship | ✅ Done |
| 3 | LLM foundation + consistency / near-dup / PII / labels checks | ✅ Done |
| 4 | HTML report (Triage layout: rail, summary strip, expandable issues) | ✅ Done |
| 5 | Package + CLI (`auditor run`), docs | ✅ Done |
| D | Live local-LLM runs (`brief`, `triage`, label judging) | ✅ Done |
| v2 | Leakage-safe evaluation (2 tasks, N=80 held-out) + readiness rubric | ✅ Done |
| Kaggle | Publish the benchmark (4 tasks, open + fresh-private, cross-model leaderboard) | ✅ Done |
| next | Config-file rules · Streamlit UI | ⏳ Next |

The LLM-assisted checks (consistency, near-duplicate, PII, labels) and the opt-in materials
formula-agreement pack are all generic engines configured by a `DatasetSpec` — none is bound to one
dataset. See [`ROADMAP.md`](ROADMAP.md) for the per-check breakdown and the design rationale.

## Flagship: LeMaterial/LeMat-Bulk

DFT materials properties (formula representations, formation energy, density of
states at the Fermi level, magnetization, …) harmonized from several source
databases. It was chosen by measuring audit-richness across candidate datasets:
unlike competition-clean ML benchmarks, LeMat-Bulk is *measurably messy*,
precisely because it reconciles databases that disagree.

A lesson worth recording: a naive sample from the cleanest config looked
deceptively pristine. Sampling **across all four configs** (`compatible_pbe`,
`compatible_pbesol`, `compatible_scan`, `non_compatible`) surfaced the real
signal: `dos_ef` ~37% null, a 3-way `functional` categorical, and many materials
recurring across functionals. Profiling before building, again.

Deterministic findings (`python -m auditor.checks --dataset lemat_bulk`, 25k-row
sample):

```
total findings: 363   (error=122, warn=241)
  near_dup.shared_content    240   one entalpic_fingerprint under several immutable_ids
  duplicates.duplicate_key   122   same immutable_id across DFT functionals
  schema.high_null_rate        1   dos_ef ~37% null (computed for only some entries)
```

The headline here is **duplicates + missingness**, not impossible values. This is
rigorous computational data, so the range check is (honestly) clean — and so, it
turns out, is the Phase-3 consistency check: profiling confirmed that every row
sharing an `immutable_id` agrees on its structure, so the data is sound on that
axis too. (The originally-planned "conflicting energies across functionals" finding
was dropped during the build: DFT total energies are not comparable across
exchange-correlation functionals, so that spread is expected physics, not a defect.)
The formula-agreement domain pack closes the last open question the same way: across
all 25k rows the three OPTIMADE formula columns, the `elements` list, and `nelements`
all agree, so the flagship is clean on that axis too. The check exists to catch the
ingest defect (mismatched formula encodings) the instant one appears.

## Origin / proving ground: NASA Meteorite Landings

The deterministic checks were first built and validated against **NASA Meteorite
Landings** (45,716 rows, 10 fields). Loaded via `auditor.load.load()`, which
normalizes structure (column names, a stable `row_id`, numeric dtypes) but
deliberately leaves bad values untouched.

Profile highlights (`python src/auditor/load.py meteorites`):

| Signal | Observation |
|---|---|
| `year` range | **301 → 2501**, at least 2 rows dated in the future |
| `(reclat, reclong) == (0, 0)` | **6,214 rows (13.6%)** parked on "null island" |
| `reclong` range | max **354.47**, outside the valid **[−180, 180]** |
| `mass_g` | min **0** (impossible), 131 missing |
| missing coords | `reclat`/`reclong` ~16% null |
| exact duplicate rows | **0** |

Three hypotheses (impossible years, null-island placeholders, out-of-range
physical values) were all **confirmed by running detectors**, not just eyeballing.
A pre-profiling hypothesis ("many exact duplicate rows") was **disproven** (zero
full-row duplicates), which saved building a check for a problem that didn't exist.

Phase-2 findings on the full meteorite dataset:

```
total findings: 6,239   (error=22, warn=6,217)
  units.null_island      6,214   rows at exactly (0, 0)
  units.out_of_range        22   longitude > 180, future years, mass <= 0
  schema.high_null_rate      3   reclat / reclong / geolocation ~16% null
  duplicates                 0   no exact-row or duplicate-id collisions
```

## Local LLM setup

The LLM-assisted checks talk to a local [vLLM](https://docs.vllm.ai) server over
its OpenAI-compatible `/v1` API (run it however you like, e.g. in WSL). No data
leaves your computer.

The client (`auditor.llm`) and the LLM-judged check (`auditor.checks.labels`) are
built and tested against a mocked client, and **degrade gracefully** when no server
is running (one `info` finding; the deterministic checks are unaffected). The current
runtime is **Qwen3-4B**, served locally by vLLM. It is a deliberately small model, which
the advisory-only design makes safe: it is asked only to orient (a summary and a "what to
check" line per issue, plausible-range notes in `brief`), never to decide what is a real
defect. It can still mis-state a domain fact (it labels `chemical_formula_anonymous` as
"anonymization for privacy" when that column is really a structural-prototype formula),
which is exactly why the model stays advisory and every hard finding is computed, not
generated. Point the client elsewhere with `AUDITOR_LLM_BASE_URL` / `AUDITOR_LLM_MODEL`. See
[Deterministic vs. the LLM](#deterministic-vs-the-llm) for exactly where the model is and
isn't in the loop.

**Reasoning models.** Reasoning models (e.g. Qwen3) need to *think* before answering. The
default strict path forces JSON-only output, which suppresses that thinking and makes a
small model confabulate — on the label benchmark it scored at the floor (0.500) until
reasoning was enabled, which took it to **1.000** on held-out data ([`benchmarks/`](benchmarks/)).
So the `labels` check **defaults to reasoning mode**; for the other LLM helpers you can opt
in with `AUDITOR_LLM_REASONING=1` (slower, but it lets the model think). If a single call is
very slow, lower vLLM's `--gpu-memory-utilization` so GPU memory doesn't page to system RAM.

## Development

```powershell
uv venv
uv pip install -e ".[cli,report,load,llm,dev]"   # everything except the heavy checks extra
python scripts/acquire_lemat.py   # fetch the flagship sample (data/ is gitignored)
uv run pytest
```

Optional dependencies are grouped by phase in `pyproject.toml` (`load`, `checks`,
`llm`, `report`, `cli`, `dev`) so the data contract and its tests install without
pulling in pandas, httpx, jinja2, or torch. Install only what you need.

## Evaluation

The deterministic checks are facts (covered by `pytest`); the only fallible part is the
advisory LLM's judgement. That is measured under a **leakage-safe** protocol — see
[`EVAL_PROTOCOL.md`](EVAL_PROTOCOL.md) (the rules), [`docs/methodology.md`](docs/methodology.md)
(the reasoning), and [`benchmarks/`](benchmarks/) (the tasks). Each task has disjoint
dev/calibration/held-out splits, balanced classes, a frozen prompt locked by hash, an automated
leakage linter, a value↔label decorrelation guard, and held-out-only reporting with confidence
intervals and dumb baselines a real model must beat. The harness is pure and model-free, so CI
needs no model.

Two tasks ship today, both reusing the product's own `build_label_prompt` / `LabelVerdict` with
**no answer-bearing context**:

| Task | What it asks | Held-out (Qwen3-4B, reasoning) |
|---|---|---|
| `labels_plausibility` | is a phase-at-STP label plausible? | **1.000**, N=80, 95% CI [0.954, 1.000], F1 1.000 |
| `element_classification` | metal / nonmetal / metalloid plausible? | **1.000**, N=80, 95% CI [0.954, 1.000], F1 1.000 |

Both beat the vocabulary-floor and majority-class baselines (0.500). The result is **reasoning
mode's doing**: the strict forced-JSON path scored at the floor (0.500) until the small model was
let to think first. A much smaller model (Qwen3.5-0.8B) sits *below* the harness's structured-output
floor — it can't emit a valid verdict under the frozen prompt — so the 1.000 is not reproducible by
just any model. The readiness rubric (above) rolls the deterministic findings into per-dimension
scores; LLM labels stay advisory and never move it.

### On Kaggle: a public cross-model leaderboard

The same benchmark is **published on [Kaggle Benchmarks](https://www.kaggle.com/benchmarks)** so
frontier models can be compared on it directly — see [`kaggle/`](kaggle/). Each domain ships as an
**open** set (the public cases above — reproducible, but a model may have seen them) and a
**fresh-private** set (newly minted, never published, so a score can't be dismissed as
memorisation). Scoring stays exact-match; each task returns `(accuracy, 95% CI)`.

```mermaid
%%{init: {'flowchart': {'curve': 'linear'}}}%%
flowchart TD
    PR["Shipped build_label_prompt<br/>frozen by SHA-256"] --> OPEN["Open set<br/>public cases · reproducible<br/>(a model may have seen them)"]
    PR --> PRIV["Fresh-private set<br/>newly minted · never published<br/>(score can't be memorisation)"]
    OPEN --> KB["Kaggle Benchmarks<br/>cross-model leaderboard"]
    PRIV --> KB
    KB --> OUT["accuracy ± 95% CI<br/>must beat the 0.500 baselines"]
```

| Model | Phase-STP open | Phase-STP private | Element open | Element private |
|---|---|---|---|---|
| Claude Haiku 4.5 | 0.988 | 0.988 | 1.000 | 1.000 |
| Gemini 3 Flash | 1.000 | 0.975 | 0.975 | 0.938 |
| Gemini 3.1 Flash-Lite | 1.000 | 1.000 | 0.988 | 0.988 |
| GLM-5 | 1.000 | 1.000 | 0.975 | 0.975 |
| Qwen3-Next-80B **Thinking** | **1.000** | **1.000** | **1.000** | **1.000** |
| Qwen3-Next-80B **Instruct** | **0.513** | **0.513** | 0.675 | 0.763 |

*(N=80 each; accuracy with 95% Wilson CI half-width ≈ ±0.023 at 1.000. Thinking scored a clean 1.000
across all four cells (both open and both private). DeepSeek V3.2 and gpt-oss-120b errored on
transient provider load (429/503) — not a property of the benchmark.)* The
headline: the **same** 80B model scores **1.000 Thinking vs 0.513 Instruct** on phase-plausibility —
the reasoning thesis, live across vendors. Four frontier models cluster near-perfect while
Qwen-Instruct sits at/near the 0.50 floor on phase, so the benchmark **discriminates** (not everyone
passes); and each model's fresh-private number tracks its open one, so contamination isn't inflating
the public scores.

## License

MIT
