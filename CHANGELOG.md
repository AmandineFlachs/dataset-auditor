# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Benchmark published to Kaggle Benchmarks** (`kaggle/`): both domains as four public, runnable
  tasks — an *open* set (the public test cases) and a *fresh-private* set (never published) each —
  with a public cross-model leaderboard. The leakage discipline carries over unchanged (frozen
  prompt, exact-match scoring, baselines as the 0.50 floor); see [`kaggle/README.md`](kaggle/README.md).
- **Cross-model leaderboard.** Claude Haiku 4.5, both Gemini 3 Flash variants, GLM-5, and
  Qwen3-Next-80B **Thinking** all score near-perfect across the four tasks; the headline is the
  **same 80B model at Thinking 1.000 vs Instruct 0.513** on phase-plausibility — the reasoning
  thesis, live across vendors. The benchmark discriminates (Qwen-Instruct at the 0.50 floor) and
  each model's fresh-private score tracks its open one (no contamination inflation).

## [0.2.0] - 2026-06-14

Leakage-safe evaluation layer + dataset-readiness rubric. `main` stays v1; this is the v2 line.

### Added

- **Leakage-safe evaluation protocol** — `EVAL_PROTOCOL.md` (scope tiers, leakage/contamination
  definitions, disjoint dev/calibration/held-out splits, prompt- and scoring-freeze,
  held-out-only reporting with confidence intervals and baselines), plus `docs/methodology.md`
  and `docs/leakage_checklist.md`.
- **Two leakage-safe benchmark tasks** (`benchmarks/`, local-only, no Kaggle SDK):
  `labels_plausibility` (phase at STP) and `element_classification` (metal / nonmetal /
  metalloid). Both reuse the shipped `build_label_prompt` / `LabelVerdict` and pass **no**
  answer-bearing context. Each has three disjoint splits, balanced classes, an automated leakage
  linter, a frozen-prompt hash, and a value↔label decorrelation guard — all enforced in CI.
  Held-out sets are **N=80 per task**.
- **Reasoning mode** in `auditor.llm` (opt-in; default-on for the `labels` check). The strict
  forced-JSON path made the small Qwen3-4B confabulate and score at the floor (0.500); letting it
  think first took it to **1.000 held-out on both domains** (95% CI [0.954, 1.000]), beating the
  vocabulary-floor and majority-class baselines.
- **Dataset-readiness rubric** — `auditor rubric` + a report panel: per-dimension scores
  (completeness, consistency, plausibility, duplication, privacy) plus an overall number, a
  deterministic roll-up of the findings. LLM-judged labels stay advisory and never move a score.

### Changed

- **The PII check always runs.** It previously scanned only the columns a spec declared in
  `pii_text_columns`; now, when none are declared, it auto-detects the text columns and scans
  them for the rigid, low-false-positive identifiers (email, SSN). Declared columns still get
  the full detector set (phone, card, IPv4). As a result the rubric's **privacy** dimension is
  assessed (not `n/a`) wherever a dataset has text columns — both flagships come back clean, so
  readiness ticks up (meteorites 93→94, LeMat 98→99).

### Notes

- A second model (Qwen3.5-0.8B) sits **below the harness's structured-output floor** — it echoes
  the schema instead of a verdict, so it produces no score. The frozen prompt was **not** relaxed
  to rescue it (that would tune on held-out data), so the 1.000 is not trivially reproducible.
- Test suite: **223 tests**, fully offline (the harness is pure and model-free).

## [0.1.0] - 2026-06-08

First public release.

### Added

- **Deterministic check families**, each returning a uniform `Finding`: schema
  (high null rate), units (range plausibility, null-island placeholders), duplicates
  (exact rows + duplicate keys), near-duplicates (shared content under distinct ids),
  cross-field consistency, PII (regex tier with masked evidence), categorical label
  plausibility, and an opt-in materials formula-agreement pack.
- **Multi-dataset architecture**: per-dataset knowledge lives in a `DatasetSpec`
  registry; the check engines stay generic. Flagship **LeMaterial/LeMat-Bulk**;
  proving ground **NASA Meteorite Landings**.
- **Found → Expected**: findings carry an optional `expected` target, populated by
  every check that has a concrete one; judgement-style checks fall back to
  Evidence → Suggested fix.
- **Advisory local-LLM layer** (vLLM, OpenAI-compatible `/v1`) that never changes a
  deterministic finding: a metadata-only research briefing (`auditor brief`), finding
  triage with a deterministic priority plus model notes (`auditor triage`), and
  LLM-judged categorical plausibility. Degrades gracefully when no server is running.
- **Self-contained HTML report** in a Triage layout: a category rail, a summary strip
  (count, severity, clean-rate), and a grouped, expandable issue stream. Per-issue
  keep / dismiss / needs-review with notes, persisted in the browser and exportable to
  CSV. System fonts, no external resources.
- **CLI** (`auditor`): `run`, `datasets`, `profile`, `brief`, `triage`.
- Test suite (141 tests, offline) and committed sample reports + briefings in
  `examples/`.

[0.2.0]: https://github.com/AmandineFlachs/dataset-auditor/releases/tag/v0.2.0
[0.1.0]: https://github.com/AmandineFlachs/dataset-auditor/releases/tag/v0.1.0
