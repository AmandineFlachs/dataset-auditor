# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[semantic versioning](https://semver.org/).

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

[0.1.0]: https://github.com/AmandineFlachs/dataset-auditor/releases/tag/v0.1.0
