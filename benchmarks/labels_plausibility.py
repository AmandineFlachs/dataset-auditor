# %%
"""Kaggle benchmark: categorical plausibility (the auditor's labels.py judgement).

Showcase task. Each case gives a model an element and a labelled phase-at-STP; the
model must judge whether the label is plausible. A vocabulary check passes any value in
{solid, liquid, gas}; only world knowledge catches mercury labelled "solid". It reuses
the SHIPPED prompt builder (``labels.build_label_prompt``) and the shipped output schema
(``LabelVerdict``), so the benchmark measures production behaviour, not a copy.

Run it (see benchmarks/README.md for the full loop):

    kaggle b init -y
    python benchmarks/labels_plausibility.py            # validate locally -> .run.json
    kaggle b t push labels-plausibility -f benchmarks/labels_plausibility.py --wait
    kaggle b t run labels-plausibility -m <model-a> -m <model-b>
"""
import pathlib
import sys

# Make `import harness` and `import auditor` work when run as `python benchmarks/...py`
# from the repo, without requiring an editable install.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

import kaggle_benchmarks as kbench

from auditor.checks.labels import LabelVerdict, build_label_prompt

import harness

# %%
@kbench.task(
    name="labels-plausibility",
    description="Judge whether a chemical element's labelled phase-at-STP is plausible "
    "(mercury labelled 'solid' is the case a vocabulary check cannot catch).",
)
def labels_plausibility(llm):
    meta = harness.load_meta("elements")
    domain = harness.resolve_domain_context(meta)
    cases = harness.load_cases(harness.case_dir("elements") / "labels.jsonl")
    for case in cases:
        rule, row = harness.label_case_to_inputs(case, meta)
        body = build_label_prompt(rule, row, list(rule.context_columns))
        verdict = llm.prompt(harness.compose_prompt(domain, body), schema=LabelVerdict)
        element = case.get("context", {}).get("element", case["value"])
        kbench.assertions.assert_equal(
            case["expected"],
            harness.label_actual(verdict),
            expectation=f"{case['id']}: '{case['value']}' for {element} should be {case['expected']}",
        )


# %%
labels_plausibility.run(kbench.llm)
