"""Grader tests: the benchmark uses the SHIPPED prompt and prepends no grounding."""

from auditor.checks.labels import LabelVerdict, build_label_prompt

from shared import grader

META = {
    "column": "phase_at_stp",
    "allowed": ["solid", "liquid", "gas"],
    "context_fields": ["element", "symbol"],
}
CASE = {
    "id": "mercury-solid",
    "value": "solid",
    "context": {"element": "Mercury", "symbol": "Hg"},
    "expected": "implausible",
    "note": "Hg is liquid at STP",
}


def test_case_to_inputs_shapes_rule_and_row():
    rule, row = grader.case_to_inputs(CASE, META)
    assert rule.column == "phase_at_stp"
    assert set(rule.context_columns) == {"element", "symbol"}
    assert row["phase_at_stp"] == "solid"
    assert row["element"] == "Mercury"


def test_case_to_prompt_is_exactly_the_shipped_prompt_with_no_extra_grounding():
    rule, row = grader.case_to_inputs(CASE, META)
    expected = build_label_prompt(rule, row, list(rule.context_columns))
    prompt = grader.case_to_prompt(CASE, META)
    assert prompt == expected  # no wrapper, no domain_context prepended
    assert "Mercury" in prompt and "solid" in prompt
    # the curator rationale is never sent to the model
    assert "liquid at STP" not in prompt


def test_verdict_and_grade_mapping():
    impl = LabelVerdict(plausible=False, confidence=0.9, reason="hg is liquid")
    pla = LabelVerdict(plausible=True, confidence=0.9, reason="ok")
    assert grader.verdict_to_label(impl) == "implausible"
    assert grader.verdict_to_label(pla) == "plausible"
    assert grader.grade_one(impl, CASE) is True   # expected implausible
    assert grader.grade_one(pla, CASE) is False
