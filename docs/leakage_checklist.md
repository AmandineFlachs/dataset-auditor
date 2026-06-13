# Leakage checklist (run before freezing any benchmark)

Work through this before freezing a task's prompt and running its `test` split. Each item
is either **[auto]** (enforced by `benchmarks/shared/leakage.py` + a test, fails CI) or
**[manual]** (human judgement — no linter can catch it). See
[`EVAL_PROTOCOL.md`](../EVAL_PROTOCOL.md) for the rules these enforce.

## Context must not contain the answer

- [auto] No context value equals the judged `value`.
- [auto] No context value contains a forbidden answer term (per the task's
  `leakage_policy.forbid_terms` — e.g. `solid`, `liquid`, `gas`, `melting point`,
  `boiling point` for phase-at-STP).
- [auto] Every context key is on the task's `meta.context_fields` allow-list (a stray
  `phase` or `melting_point` key fails).
- [auto] The task carries **no** `domain_context` (the field that caused the original
  leak). `meta.json` must not define a non-empty `domain_context`.
- [manual] No context field lets the answer be *derived* trivially (e.g. a numeric field
  whose threshold alone settles the label). Prefer fields that require world knowledge to
  connect to the answer.
- [manual] The `note`/rationale field is never sent to the model (it is curator-only).

## Ground truth must be sound

- [auto] Every `expected` value is one of the allowed verdicts.
- [auto] Every judged `value` is in the task's allowed vocabulary (catches typos/mislabels).
- [manual] Each label is correct on the merits — spot-check a sample against an
  authoritative source. (If several capable models later disagree with a label for the same
  sound reason, suspect the label, not the models.)
- [manual] Classes are roughly balanced; "implausible" cases are genuine, not strawmen.

## Splits must be clean

- [auto] No case id appears in more than one split.
- [auto] No `(value, context)` signature appears in more than one split.
- [manual] `dev`/`calibration` were the only splits inspected during development; `test`
  was not opened.

## Pretraining-contamination hygiene

- [manual] Cases are curated/planted, not copied verbatim from a well-known public dataset.
- [manual] If a case is unavoidably "famous" (e.g. mercury is liquid), it is acceptable
  only because the *task* is to test that exact world knowledge — note it, and don't let
  such cases dominate the set.

## Freeze readiness

- [manual] Prompt is final; its identity hash is recorded in `meta.json` + `PROMPT_FREEZE.md`.
- [manual] Scorer version in `meta.json` matches `shared.metrics.SCORER_VERSION`.
- [manual] You are ready to report held-out numbers *with* a confidence interval and the
  two baselines, citing task/split/N/hash/scorer/model/date.

---

If any **[auto]** item fails, CI is red and the task cannot ship. If any **[manual]** item
is unmet, do not freeze — fix the cases first.
