"""Model-free tests for capturing report decisions as benchmark cases.

No LLM, no browser: feed synthetic issue groups + a decisions export to the pure
converters and assert the produced cases are byte-compatible with the benchmark harness
(the shape contract that lets `auditor select-model` grade them).
"""

import json

from auditor.capture import (
    issue_id,
    to_cases,
    verdict_for,
    write_cases,
)
from auditor.datasets import get
from auditor.modelselect import case_to_issue, load_cases, score_model  # noqa: F401 (shape contract)
from auditor.triage import build_verdict_prompt


# Two canonical issue groups (the shape triage.issue_groups produces).
GROUPS = [
    {"check": "duplicates.duplicate_key", "field": "immutable_id", "severity": "error",
     "count": 122, "message": "Duplicate immutable_id.", "samples": ["id=mp-149"], "priority": "high", "suggested_fix": "x"},
    {"check": "units.out_of_range", "field": "nsites", "severity": "warn",
     "count": 1, "message": "nsites below 1.", "samples": ["nsites=0"], "priority": "medium", "suggested_fix": "y"},
]


def _decision(group, status, note=""):
    return {"dataset": "lemat_bulk", "check": group["check"], "field": group["field"],
            "message": group["message"], "evidence": group["samples"][0],
            "severity": group["severity"], "count": group["count"], "status": status, "note": note}


# -- verdict aggregation ------------------------------------------------------


def test_verdict_for_maps_keep_and_dismiss():
    assert verdict_for(["keep"]) == "real_defect"
    assert verdict_for(["dismiss"]) == "expected_artifact"
    assert verdict_for(["keep", "keep"]) == "real_defect"


def test_verdict_for_conflict_and_undecided_are_none():
    assert verdict_for(["keep", "dismiss"]) is None     # genuine conflict
    assert verdict_for(["review"]) is None
    assert verdict_for([]) is None


# -- to_cases -----------------------------------------------------------------


def test_to_cases_labels_kept_and_dismissed():
    export = [_decision(GROUPS[0], "dismiss", "expected across functionals"),
              _decision(GROUPS[1], "keep")]
    cases, summary = to_cases(GROUPS, export)
    by_check = {c["check"]: c for c in cases}
    assert by_check["duplicates.duplicate_key"]["expected"] == "expected_artifact"
    assert by_check["duplicates.duplicate_key"]["note"] == "expected across functionals"
    assert by_check["units.out_of_range"]["expected"] == "real_defect"
    assert summary == {"labeled": 2, "conflict": 0, "undecided": 0}


def test_to_cases_drops_undecided_and_conflict():
    export = [
        _decision(GROUPS[0], "keep"),
        _decision(GROUPS[0], "dismiss"),   # conflicts with the keep above -> dropped
        # GROUPS[1] has no decision -> undecided
    ]
    cases, summary = to_cases(GROUPS, export)
    assert cases == []
    assert summary == {"labeled": 0, "conflict": 1, "undecided": 1}


def test_to_cases_carries_samples_and_count_from_groups():
    cases, _ = to_cases(GROUPS, [_decision(GROUPS[0], "dismiss")])
    case = cases[0]
    assert case["samples"] == ["id=mp-149"] and case["count"] == 122


def test_issue_id_is_stable_and_distinct():
    a = issue_id("units.out_of_range", "nsites", "below 1")
    assert a == issue_id("units.out_of_range", "nsites", "below 1")          # stable
    assert a != issue_id("units.out_of_range", "nsites", "above 3")          # message matters


# -- shape contract: a captured case must be gradable by the benchmark path ---


def test_captured_case_round_trips_through_the_benchmark_shape():
    cases, _ = to_cases(GROUPS, [_decision(GROUPS[0], "dismiss"), _decision(GROUPS[1], "keep")])
    spec = get("lemat_bulk")
    for case in cases:
        # The exact path score_model/the harness take: project -> build the shipped prompt.
        issue = case_to_issue(case)
        prompt = build_verdict_prompt(issue, spec)
        assert case["check"] in prompt and case["expected"] in ("real_defect", "expected_artifact")


# -- write_cases (merge by id) ------------------------------------------------


def test_write_cases_appends_and_dedupes_by_id(tmp_path):
    out = tmp_path / "triage_verdict.jsonl"
    first, _ = to_cases(GROUPS, [_decision(GROUPS[0], "dismiss")])
    assert write_cases(first, out) == 1
    # Re-capture the same issue with the opposite verdict: same id overwrites, not appends.
    again, _ = to_cases(GROUPS, [_decision(GROUPS[0], "keep")])
    assert write_cases(again, out) == 1
    reloaded = load_cases(out)
    assert len(reloaded) == 1 and reloaded[0]["expected"] == "real_defect"
    # And a brand-new issue appends.
    more, _ = to_cases(GROUPS, [_decision(GROUPS[1], "keep")])
    assert write_cases(more, out) == 2


def test_write_cases_overwrite_replaces(tmp_path):
    out = tmp_path / "triage_verdict.jsonl"
    write_cases(to_cases(GROUPS, [_decision(GROUPS[0], "dismiss")])[0], out)
    write_cases(to_cases(GROUPS, [_decision(GROUPS[1], "keep")])[0], out, append=False)
    reloaded = load_cases(out)
    assert len(reloaded) == 1 and reloaded[0]["check"] == "units.out_of_range"
    # produced file is valid JSONL
    for line in out.read_text(encoding="utf-8").splitlines():
        json.loads(line)
