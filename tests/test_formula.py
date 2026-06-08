"""Tests for the opt-in formula-agreement domain pack (checks/formula.py).

Pure pandas, no network: a tiny DataFrame of OPTIMADE-style formula rows exercises
the parser, the GCD reduction, each cross-check, and the dormant-when-unconfigured
contract. The real LeMat-Bulk sample is honestly clean, so a *crafted* defect is what
proves the check actually fires.
"""

from __future__ import annotations

import pandas as pd

from auditor.checks import formula
from auditor.datasets import FormulaRule

# Names the full set of columns LeMat-Bulk carries.
RULE = FormulaRule(
    reduced="chemical_formula_reduced",
    descriptive="chemical_formula_descriptive",
    anonymous="chemical_formula_anonymous",
    elements="elements",
    nelements="nelements",
)


def _row(descriptive, reduced, anonymous, elements, nelements, row_id=0):
    return {
        "row_id": row_id,
        "chemical_formula_descriptive": descriptive,
        "chemical_formula_reduced": reduced,
        "chemical_formula_anonymous": anonymous,
        "elements": elements,
        "nelements": nelements,
    }


def _df(*rows):
    return pd.DataFrame(list(rows))


# -- parsing / reduction ------------------------------------------------------


def test_parse_spaced_and_compact_agree():
    assert formula._parse("Cd2 In1 P1") == {"Cd": 2, "In": 1, "P": 1}
    assert formula._parse("Cd2InP") == {"Cd": 2, "In": 1, "P": 1}


def test_parse_rejects_garbage():
    assert formula._parse("2Fe") is None       # digit-first
    assert formula._parse("xyz") is None        # lone lowercase, no leading capital
    assert formula._parse("") is None
    assert formula._parse(None) is None


def test_reduce_divides_by_gcd():
    assert formula._reduce({"Fe": 4, "O": 6}) == {"Fe": 2, "O": 3}
    assert formula._reduce({"H": 1, "O": 4, "V": 2}) == {"H": 1, "O": 4, "V": 2}  # gcd 1, unchanged


# -- the happy path -----------------------------------------------------------


def test_consistent_triple_yields_no_findings():
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A2BC", "Cd-In-P", 3))
    assert formula.check(df, rules=(RULE,)) == []


def test_gcd_scaled_descriptive_still_agrees():
    # descriptive Fe4 O6 reduces to Fe2O3, matching the reduced column -> no finding.
    df = _df(_row("Fe4 O6", "Fe2O3", "A3B2", "Fe-O", 2))
    assert formula.check(df, rules=(RULE,)) == []


# -- each comparison fires on a crafted defect --------------------------------


def test_anonymous_disagreement_is_an_error():
    # reduced counts are [2,1,1] (A2BC); anonymous claims A3BC ([3,1,1]).
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A3BC", "Cd-In-P", 3))
    out = formula.check(df, rules=(RULE,))
    assert [f.check for f in out] == ["formula.mismatch"]
    assert out[0].severity.value == "error"
    assert out[0].field == "chemical_formula_anonymous"


def test_descriptive_disagreement_is_an_error():
    # descriptive says Cd3 (->[3,1,1]) but reduced anchor is Cd2InP (->[2,1,1]).
    df = _df(_row("Cd3 In1 P1", "Cd2InP", "A2BC", "Cd-In-P", 3))
    out = formula.check(df, rules=(RULE,))
    assert any(f.field == "chemical_formula_descriptive" and f.check == "formula.mismatch" for f in out)


def test_elements_list_disagreement_is_flagged():
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A2BC", "Cd-In-As", 3))  # P swapped for As in the list
    out = formula.check(df, rules=(RULE,))
    assert any(f.field == "elements" for f in out)


def test_nelements_disagreement_is_flagged():
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A2BC", "Cd-In-P", 2))  # 3 elements, declared 2
    out = formula.check(df, rules=(RULE,))
    assert any(f.field == "nelements" for f in out)


def test_unparseable_reduced_is_a_warning_not_a_crash():
    df = _df(_row("Cd2 In1 P1", "2Cd-bad", "A2BC", "Cd-In-P", 3))
    out = formula.check(df, rules=(RULE,))
    assert [f.check for f in out] == ["formula.unparseable"]
    assert out[0].severity.value == "warn"


# -- dormant / robustness -----------------------------------------------------


def test_no_rules_means_silent():
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A2BC", "Cd-In-P", 3))
    assert formula.check(df, rules=()) == []


def test_missing_anchor_column_is_a_noop():
    # A spec naming columns absent from the data must not raise, just stay silent.
    df = pd.DataFrame({"row_id": [0], "something_else": ["x"]})
    assert formula.check(df, rules=(RULE,)) == []


def test_missing_values_are_skipped_not_flagged():
    df = _df(_row("Cd2 In1 P1", "Cd2InP", "A2BC", None, None))  # optional cross-checks absent
    assert formula.check(df, rules=(RULE,)) == []
