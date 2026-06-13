"""Leakage-linter tests — the automated half of the leakage checklist. Model-free."""

from shared import cases, leakage

META = {
    "column": "phase_at_stp",
    "allowed": ["solid", "liquid", "gas"],
    "expected_values": ["plausible", "implausible"],
    "context_fields": ["element", "symbol", "atomic_number", "period"],
    "leakage_policy": {"no_domain_context": True, "forbid_terms": ["solid", "liquid", "gas", "melting", "boiling"]},
}


def _case(**ctx):
    return {"id": "c", "value": "solid", "context": ctx, "expected": "implausible"}


def test_shipped_task_has_no_leakage():
    allc = []
    for split in cases.SPLITS:
        allc += cases.load_split("labels_plausibility", split)
    assert leakage.leakage_check(allc, cases.load_meta("labels_plausibility")).ok


def test_clean_case_passes():
    assert leakage.leakage_check([_case(element="Mercury", symbol="Hg")], META).ok


def test_forbidden_term_in_context_is_caught():
    rep = leakage.leakage_check([_case(element="Mercury", hint="it is a liquid")], META)
    assert not rep.ok
    reasons = " ".join(h.reason for h in rep.hits)
    assert "forbidden term" in reasons or "allow-list" in reasons


def test_context_repeating_the_value_is_caught():
    rep = leakage.leakage_check([_case(element="Mercury", symbol="solid")], META)
    assert not rep.ok and any("judged value" in h.reason for h in rep.hits)


def test_stray_context_key_is_caught():
    rep = leakage.leakage_check([_case(element="Mercury", phase="x")], META)
    assert not rep.ok and any("allow-list" in h.reason for h in rep.hits)


def test_domain_context_on_meta_is_caught():
    meta = {**META, "domain_context": "every element is solid, liquid or gas"}
    assert not leakage.leakage_check([_case(element="Mercury")], meta).ok


def test_bad_ground_truth_is_caught():
    bad_expected = {"id": "x", "value": "solid", "context": {"element": "Iron"}, "expected": "maybe"}
    bad_value = {"id": "y", "value": "plasma", "context": {"element": "Iron"}, "expected": "plausible"}
    rep = leakage.leakage_check([bad_expected, bad_value], META)
    assert not rep.ok
