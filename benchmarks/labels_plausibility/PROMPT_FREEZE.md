# Frozen prompt — labels-plausibility

Frozen on **2026-06-13**. Identity hash (see `meta.json` → `frozen_prompt.hash`):

```
sha256:03bab39d5ec0e53c73e1f48edfa8013861b8bc355ffd47d934fa95d624e3ff2f
```

The hash is a SHA-256 over the production prompt builder id
(`auditor.checks.labels.build_label_prompt`), the `LabelVerdict` JSON schema, and the
rendered prompt **template** below (case values masked to `<VALUE>` / `<CTX>`). Any change
to the shipped prompt changes this hash and fails `tests/test_bench_freeze.py`, forcing a
conscious re-freeze and a fresh held-out run. See `EVAL_PROTOCOL.md` §5.

The benchmark passes **no** `domain_context` (the answer-bearing channel that leaked in the
removed v2 benchmark). The phrase "domain context" inside the template below is the shipped
builder's own generic wording, not an injected grounding block.

## Frozen template

```
Column 'phase_at_stp' has value '<VALUE>' for this row.
Known valid values: solid, liquid, gas.
Other fields for the same row:
  element=<CTX>
  symbol=<CTX>
  atomic_number=<CTX>
  period=<CTX>
Is '<VALUE>' a plausible value for 'phase_at_stp' given these fields and the domain context? Answer plausible=false ONLY if it clearly conflicts; treat borderline or uncertain cases as plausible=true and lower your confidence.
```

## Re-freezing

If the production prompt legitimately changes:
1. Run `python -c "from shared import cases, freeze; print(freeze.prompt_identity(cases.load_meta('labels_plausibility')))"` (with `PYTHONPATH=src;benchmarks`).
2. Update `meta.json` → `frozen_prompt.hash` + `frozen_at`, and this file's template/hash.
3. Re-run the held-out `test` split; prior numbers no longer apply.
