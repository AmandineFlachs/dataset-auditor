# dataset-auditor on Kaggle Benchmarks

The leakage-safe label benchmark from [`benchmarks/`](../benchmarks/), published as runnable
**Kaggle Benchmarks** so frontier models can be compared on it directly. Kaggle runs the eval
against its own model catalog and builds a public leaderboard; scoring stays deterministic
(exact-match), so the defensibility of the local protocol carries over unchanged.

## The four published tasks

Each domain ships as **two** tasks — an *open* set and a *fresh-private* set:

| Task | Set | Leaderboard |
|---|---|---|
| `dataset-auditor-labels-plausibility-open` | open (public cases) | [link](https://www.kaggle.com/benchmarks/tasks/amandineflachs/dataset-auditor-labels-plausibility-open) |
| `dataset-auditor-element-classification-open` | open (public cases) | [link](https://www.kaggle.com/benchmarks/tasks/amandineflachs/dataset-auditor-element-classification-open) |
| `dataset-auditor-labels-plausibility-private` | fresh private | [link](https://www.kaggle.com/benchmarks/tasks/amandineflachs/dataset-auditor-labels-plausibility-private) |
| `dataset-auditor-element-classification-private` | fresh private | [link](https://www.kaggle.com/benchmarks/tasks/amandineflachs/dataset-auditor-element-classification-private) |

**Why two sets.** The `benchmarks/*/test.jsonl` cases are committed to a public GitHub repo, so a
frontier model may have trained on them — a perfect score there could be memorisation. The **open**
set is the reproducible number (anyone can rerun it). The **fresh-private** set uses the project's
own vetted facts over the same known elements, projected onto a minimal `{element, symbol}` context
so every instance is provably disjoint from all public splits, and is **never published** (this
directory's `private/` is gitignored; the tasks were published with `--no-publish-backing-notebook`
so the answer key stays server-side). A score on the private set cannot be dismissed as memorisation.

## Results (accuracy ± 95% CI, N=80)

| Model | Phase-STP open | Phase-STP private | Element open | Element private |
|---|---|---|---|---|
| Claude Haiku 4.5 | 0.988 | 0.988 | 1.000 | 1.000 |
| Gemini 3 Flash | 1.000 | 0.975 | 0.975 | 0.938 |
| Gemini 3.1 Flash-Lite | 1.000 | 1.000 | 0.988 | 0.988 |
| GLM-5 | 1.000 | 1.000 | 0.975 | 0.975 |
| Qwen3-Next-80B **Thinking** | **1.000** | † | † | † |
| Qwen3-Next-80B **Instruct** | **0.513** | **0.513** | 0.675 | 0.763 |
| DeepSeek V3.2 / gpt-oss-120b | errored | errored | errored | errored |

† Thinking completed phase-open (the headline cell) then hit the per-call quota wall: each uncapped
`reasoning="high"` call reserves ~$0.31, which exceeded the day's remaining credit after the other
five models ran. A `max_tokens` cap would lower the reservation but `reasoning="high"` sets a
server-side thinking budget >24576, so any cap below it 400s Anthropic models and truncates thinking
models — uncapped is the only valid config. The three cells need a fresh credit window, not a code
change.

*Local reference:* Qwen3-4B in reasoning mode scores **1.000** on both domains (see
[`benchmarks/`](../benchmarks/)). *Deterministic floor:* the vocabulary and majority-class baselines
sit at **0.500** (printed by each task file's `__main__`) — a model must beat that with world
knowledge.

**Headline.** Same 80B model: the **Thinking** variant scores 1.000 on phase-plausibility, the
**Instruct** (non-reasoning) variant 0.513 — at the random-guess floor. That is the project's
"reasoning beats forced/terse output" thesis, reproduced across vendors on Kaggle's infrastructure.
The benchmark *discriminates* (four frontier models cluster near-perfect, Qwen-Instruct sits at the
floor on phase), and each model's fresh-private number tracks its open one (no contamination
inflation). DeepSeek V3.2 and gpt-oss-120b errored on transient provider load (429 heavy-load /
503 unreachable) on every attempt — a provider state, not a property of the benchmark.

## Design (per task file)

Each `*_task.py` is self-contained — no `auditor` import at runtime:

- **Prompt** is byte-identical to the shipped `build_label_prompt`; the frozen-prompt SHA was
  verified at generation time. Cases are embedded as pre-rendered prompts + golden labels.
- **A single `@kbench.task` run per model** returning `tuple[float, float]` = (accuracy, 95% CI
  half-width), so the leaderboard renders the interval. The 80 cases run concurrently inside the
  task. `reasoning="high"` mirrors the shipped check's winning configuration; the free-text verdict
  is parsed deterministically.
- **Scoring/baselines** (Wilson CI, F1, vocabulary-floor, majority-class) are ported from
  `benchmarks/shared/` and run in `__main__` for the deterministic floor.

## Regenerate / validate locally

```bash
# Regenerate the open task files from benchmarks/ (verifies frozen-prompt SHA + leakage linter):
PYTHONUTF8=1 PYTHONPATH="src;benchmarks" python kaggle/build_open_tasks.py

# Deterministic baselines only (no model):
KAGGLE_BENCH_NOAUTORUN=1 PYTHONUTF8=1 python kaggle/labels_plausibility_open_task.py

# Score against a LOCAL vLLM model (no Kaggle account needed) via the adapter:
AUDITOR_LLM_MODEL=Qwen/Qwen3-4B PYTHONUTF8=1 python kaggle/run_local.py kaggle/labels_plausibility_open_task.py
```

Publishing/running on Kaggle uses the separate `kaggle` CLI (`pip install kaggle`,
`kaggle auth login`, `kaggle benchmarks init`). See the generator headers for details. The
fresh-private generator and its outputs live under `private/` and are gitignored on purpose.
