# Frozen prompt — element-classification

Frozen on **2026-06-13**. Identity hash (see `meta.json` → `frozen_prompt.hash`):

```
sha256:d7e4a5d1556c88faa0554fe53e9fe7beae82f5ccce375771f9c091540f883672
```

Same scheme as `labels_plausibility` (see EVAL_PROTOCOL.md §5): a SHA-256 over the shipped
`auditor.checks.labels.build_label_prompt`, the `LabelVerdict` schema, and the rendered
prompt template with case values masked. Any change to the shipped prompt changes this hash
and fails `tests/test_bench_freeze.py`. The benchmark passes **no** `domain_context`.

## Frozen template

```
Column 'classification' has value '<VALUE>' for this row.
Known valid values: metal, nonmetal, metalloid.
Other fields for the same row:
  element=<CTX>
  symbol=<CTX>
  atomic_number=<CTX>
  period=<CTX>
Is '<VALUE>' a plausible value for 'classification' given these fields and the domain context? Answer plausible=false ONLY if it clearly conflicts; treat borderline or uncertain cases as plausible=true and lower your confidence.
```

## Re-freezing
If the production prompt legitimately changes: recompute with
`python -c "from shared import cases, freeze; print(freeze.prompt_identity(cases.load_meta('element_classification')))"`
(`PYTHONPATH=src;benchmarks`), update `meta.json` + this file, and re-run the held-out split.
