"""Offline tests for the Kaggle-benchmark plumbing in ``benchmarks/``.

No model and no Kaggle SDK are contacted: these exercise the pure prompt builders
(reused by the tasks), the fixture loader/grader in ``benchmarks/harness.py``, and the
golden cases themselves. ``benchmarks`` is on the pytest path (see pyproject), but the
kbench task files are never imported here — they call ``.run()`` at import time.
"""

from auditor.checks.labels import LabelVerdict, build_label_prompt
from auditor.datasets import get
from auditor.triage import VerdictResult, build_verdict_prompt

import harness


# -- prompt builders (the real prompts the tasks evaluate) --------------------


def test_build_label_prompt_includes_value_context_and_vocab():
    rule, row = harness.label_case_to_inputs(
        {"value": "solid", "context": {"element": "Mercury", "symbol": "Hg"}},
        {"column": "phase_at_stp", "allowed": ["solid", "liquid", "gas"]},
    )
    p = build_label_prompt(rule, row, list(rule.context_columns))
    assert "phase_at_stp" in p and "solid" in p and "Mercury" in p
    assert "solid, liquid, gas" in p  # the closed vocabulary is shown to the model


def test_build_verdict_prompt_counters_the_anchoring_that_disabled_it():
    spec = get("lemat_bulk")
    issue = {
        "check": "duplicates.duplicate_key",
        "field": "immutable_id",
        "severity": "error",
        "count": 122,
        "message": "Duplicate 'immutable_id' value; this column is expected to be unique.",
        "samples": ["immutable_id=mp-149"],
    }
    p = build_verdict_prompt(issue, spec)
    assert "immutable_id" in p and "122" in p
    assert "real_defect" in p and "expected_artifact" in p
    # It must explicitly tell the model NOT to treat a flag / high severity as proof of
    # a defect — the exact mistake a 14B made on this case.
    assert "severity" in p.lower()


# -- grading ------------------------------------------------------------------


def test_grade_label_maps_plausible_bool_to_vocabulary():
    assert harness.grade_label(LabelVerdict(plausible=False, confidence=0.9, reason="x"), {"expected": "implausible"})
    assert harness.grade_label(LabelVerdict(plausible=True, confidence=0.9, reason="x"), {"expected": "plausible"})
    assert not harness.grade_label(LabelVerdict(plausible=True, confidence=0.9, reason="x"), {"expected": "implausible"})


def test_grade_verdict_compares_the_label():
    yes = VerdictResult(verdict="expected_artifact", confidence=0.8, reason="x")
    no = VerdictResult(verdict="real_defect", confidence=0.8, reason="x")
    assert harness.grade_verdict(yes, {"expected": "expected_artifact"})
    assert not harness.grade_verdict(no, {"expected": "expected_artifact"})


# -- domain context resolution / composition ----------------------------------


def test_resolve_domain_context_from_spec_or_meta():
    assert harness.resolve_domain_context({"spec": "lemat_bulk"}) == get("lemat_bulk").domain_context
    assert harness.resolve_domain_context({"domain_context": "abc"}) == "abc"
    assert harness.resolve_domain_context({}) == ""


def test_compose_prompt_puts_domain_first():
    assert harness.compose_prompt("CTX", "BODY").startswith("CTX")
    assert "BODY" in harness.compose_prompt("CTX", "BODY")
    assert harness.compose_prompt("", "BODY") == "BODY"  # no leading blank lines


def test_verdict_case_to_issue_drops_grading_keys():
    case = {"id": "x", "check": "c", "field": "f", "severity": "error", "count": 2,
            "message": "m", "samples": ["s"], "expected": "real_defect", "note": "n"}
    issue = harness.verdict_case_to_issue(case)
    assert issue == {"check": "c", "field": "f", "severity": "error", "count": 2,
                     "message": "m", "samples": ["s"]}
    assert "expected" not in issue and "note" not in issue  # golden label never leaks in


# -- the golden fixtures themselves (guards on the labelled ground truth) ------


def test_elements_fixtures_are_valid():
    meta = harness.load_meta("elements")
    cases = harness.load_cases(harness.case_dir("elements") / "labels.jsonl")
    assert cases
    allowed = set(meta["allowed"])
    ids = set()
    for c in cases:
        assert c["value"] in allowed
        assert c["expected"] in {"plausible", "implausible"}
        assert c["id"] not in ids  # ids are unique
        ids.add(c["id"])
    merc = next(c for c in cases if c["id"] == "mercury-solid")
    assert merc["expected"] == "implausible"  # the iconic case is labelled correctly


def test_lemat_verdict_fixtures_are_valid():
    cases = harness.load_cases(harness.case_dir("lemat_bulk") / "triage_verdict.jsonl")
    assert cases
    for c in cases:
        assert c["expected"] in {"real_defect", "expected_artifact"}
        for k in ("id", "check", "field", "severity", "count", "message"):
            assert k in c
    labels = {c["id"]: c["expected"] for c in cases}
    assert labels["dup-immutable-id"] == "expected_artifact"  # the case the 14B failed
    assert labels["formula-mismatch"] == "real_defect"
    # a benchmark needs both classes present to discriminate models
    assert {"real_defect", "expected_artifact"} <= set(labels.values())


def test_real_fixture_case_builds_the_shipped_prompt_end_to_end():
    # A real case flows through the harness into the shipped builder with no LLM.
    meta = harness.load_meta("elements")
    case = harness.load_cases(harness.case_dir("elements") / "labels.jsonl")[0]
    rule, row = harness.label_case_to_inputs(case, meta)
    p = build_label_prompt(rule, row, list(rule.context_columns))
    assert case["value"] in p and case["context"]["element"] in p
