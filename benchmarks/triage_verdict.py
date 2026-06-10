# %%
"""Kaggle benchmark: real-defect-vs-expected-artifact triage verdict.

The genuinely-useful task. For each aggregated audit issue the model must judge whether
it is a GENUINE DEFECT or an EXPECTED ARTIFACT the dataset's domain explains. This is the
verdict the shipped triage deliberately WITHHOLDS: a 14B could not do it (it called the
~122 cross-functional duplicate ids a defect, anchoring on the "expected to be unique"
message and error severity), so it was removed rather than ship a wrong judgement. This
benchmark measures whether a better model can do it - a passing model is the evidence to
reintroduce the verdict to the product.

It uses ``triage.build_verdict_prompt`` / ``triage.VerdictResult`` (authored for exactly
this) and the real ``lemat_bulk`` ``domain_context`` (read from the DatasetSpec).

    kaggle b init -y
    python benchmarks/triage_verdict.py                 # validate locally -> .run.json
    kaggle b t push triage-verdict -f benchmarks/triage_verdict.py --wait
    kaggle b t run triage-verdict -m <model-a> -m <model-b>
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

import kaggle_benchmarks as kbench

from auditor.datasets import get
from auditor.triage import VerdictResult, build_verdict_prompt

import harness

# %%
@kbench.task(
    name="triage-verdict",
    description="Judge whether an aggregated data-quality issue on LeMat-Bulk is a real "
    "defect or an expected artifact the domain explains (the verdict the shipped triage "
    "withholds because a 14B got it wrong).",
)
def triage_verdict(llm):
    meta = harness.load_meta("lemat_bulk")
    spec = get(meta["spec"])
    domain = spec.domain_context
    cases = harness.load_cases(harness.case_dir("lemat_bulk") / "triage_verdict.jsonl")
    for case in cases:
        issue = harness.verdict_case_to_issue(case)
        body = build_verdict_prompt(issue, spec)
        result = llm.prompt(harness.compose_prompt(domain, body), schema=VerdictResult)
        kbench.assertions.assert_equal(
            case["expected"],
            result.verdict,
            expectation=f"{case['id']}: {issue['check']} on {issue.get('field')} should be {case['expected']}",
        )


# %%
triage_verdict.run(kbench.llm)
