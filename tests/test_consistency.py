"""Crafted-row tests for the group-consistency check.

The real datasets are honestly consistent on every axis we can check, so these
planted fixtures are what prove the engine actually fires. The final test runs the
*real* LeMat-Bulk rule against a deliberately corrupted material to show the
configured check catches a harmonization defect the moment one exists.
"""

import pandas as pd

from auditor.checks import consistency
from auditor.datasets import ConsistencyRule, LEMAT_BULK


# -- exact mode ---------------------------------------------------------------


def test_exact_mismatch_flags_every_row_in_the_group():
    # Same id, but nsites disagrees -> the two records aren't the same entity.
    df = pd.DataFrame(
        {
            "row_id": [0, 1, 2],
            "id": ["a", "a", "b"],
            "nsites": [8, 9, 4],
        }
    )
    rule = ConsistencyRule(group_by="id", columns=("nsites",), mode="exact")
    findings = consistency.check(df, [rule])
    assert {f.row_id for f in findings} == {0, 1}  # both rows of the bad group
    assert all(f.check == "consistency.group_mismatch" for f in findings)
    assert all(f.severity.value == "error" for f in findings)
    assert all(f.field == "nsites" for f in findings)


def test_exact_consistent_group_yields_nothing():
    # Same id appearing twice but agreeing on the invariant -> not a finding.
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "nsites": [8, 8]})
    rule = ConsistencyRule(group_by="id", columns=("nsites",), mode="exact")
    assert consistency.check(df, [rule]) == []


def test_exact_treats_missing_as_a_disagreement():
    # Set in one row, missing in the other -> still inconsistent.
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "formula": ["NaCl", None]})
    rule = ConsistencyRule(group_by="id", columns=("formula",), mode="exact")
    findings = consistency.check(df, [rule])
    assert {f.row_id for f in findings} == {0, 1}
    assert "<missing>" in findings[0].evidence


def test_singleton_groups_are_never_flagged():
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "b"], "nsites": [8, 9]})
    rule = ConsistencyRule(group_by="id", columns=("nsites",), mode="exact")
    assert consistency.check(df, [rule]) == []


# -- numeric mode -------------------------------------------------------------


def test_numeric_spread_beyond_absolute_tolerance_fires():
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "x": [10.0, 13.0]})
    rule = ConsistencyRule(group_by="id", columns=("x",), mode="numeric", tolerance=1.0)
    findings = consistency.check(df, [rule])
    assert {f.row_id for f in findings} == {0, 1}
    assert findings[0].check == "consistency.value_spread"
    assert findings[0].severity.value == "warn"


def test_numeric_within_tolerance_is_quiet():
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "x": [10.0, 10.5]})
    rule = ConsistencyRule(group_by="id", columns=("x",), mode="numeric", tolerance=1.0)
    assert consistency.check(df, [rule]) == []


def test_numeric_normalize_by_compares_per_unit():
    # Totals differ (10 vs 20) but per-atom they're identical (5 vs 5) -> quiet.
    df = pd.DataFrame(
        {"row_id": [0, 1], "id": ["a", "a"], "energy": [10.0, 20.0], "nsites": [2, 4]}
    )
    rule = ConsistencyRule(
        group_by="id", columns=("energy",), mode="numeric",
        tolerance=0.1, normalize_by="nsites",
    )
    assert consistency.check(df, [rule]) == []


def test_numeric_relative_tolerance_scales_with_magnitude():
    # spread 100 on a ~1000 magnitude is within 20%, but not within 5%.
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "x": [1000.0, 1100.0]})
    lenient = ConsistencyRule(group_by="id", columns=("x",), mode="numeric", tolerance=0.2, relative=True)
    strict = ConsistencyRule(group_by="id", columns=("x",), mode="numeric", tolerance=0.05, relative=True)
    assert consistency.check(df, [lenient]) == []
    assert len(consistency.check(df, [strict])) == 2


def test_numeric_relative_zero_median_degrades_to_absolute_zero():
    # median 0 -> limit = tolerance*0 = 0, so any non-zero spread fires regardless of tol.
    df = pd.DataFrame({"row_id": [0, 1, 2], "id": ["a", "a", "a"], "x": [-5.0, 0.0, 5.0]})
    rule = ConsistencyRule(group_by="id", columns=("x",), mode="numeric", tolerance=0.5, relative=True)
    assert {f.row_id for f in consistency.check(df, [rule])} == {0, 1, 2}


def test_numeric_zero_denominator_does_not_manufacture_a_finding():
    # energy/nsites with nsites=0 -> inf; must be dropped as non-finite, not flagged.
    df = pd.DataFrame({"row_id": [0, 1], "id": ["a", "a"], "energy": [10.0, 20.0], "nsites": [0, 0]})
    rule = ConsistencyRule(group_by="id", columns=("energy",), mode="numeric", tolerance=0.1, normalize_by="nsites")
    assert consistency.check(df, [rule]) == []


# -- guards -------------------------------------------------------------------


def test_no_rules_yields_nothing():
    df = pd.DataFrame({"row_id": [0], "id": ["a"]})
    assert consistency.check(df, []) == []


def test_missing_group_column_is_skipped():
    df = pd.DataFrame({"row_id": [0, 1], "x": [1, 2]})
    rule = ConsistencyRule(group_by="absent", columns=("x",), mode="exact")
    assert consistency.check(df, [rule]) == []


# -- the real LeMat rule, on planted data -------------------------------------


def test_real_lemat_rule_is_clean_on_consistent_material():
    # Same immutable_id under two functionals, identical structure, differing
    # energy. This is the *expected* shape; it must NOT fire.
    df = pd.DataFrame(
        {
            "row_id": [0, 1],
            "immutable_id": ["agm-1", "agm-1"],
            "functional": ["pbe", "scan"],
            "nsites": [8, 8],
            "nelements": [3, 3],
            "nperiodic_dimensions": [3, 3],
            "chemical_formula_reduced": ["C4NiTm3", "C4NiTm3"],
            "chemical_formula_descriptive": ["C4NiTm3", "C4NiTm3"],
            "chemical_formula_anonymous": ["A4B3C", "A4B3C"],
            "elements": ["C-Ni-Tm", "C-Ni-Tm"],
            "energy": [-58.4, -62.4],  # legitimately differs across functionals
        }
    )
    assert consistency.check(df, LEMAT_BULK.consistency_rules) == []


def test_real_lemat_rule_catches_harmonization_defect():
    # Same id, but the two records describe different structures (nsites 8 vs 9,
    # different formula) -> a genuine bug the configured rule should surface.
    df = pd.DataFrame(
        {
            "row_id": [0, 1],
            "immutable_id": ["agm-1", "agm-1"],
            "functional": ["pbe", "scan"],
            "nsites": [8, 9],
            "nelements": [3, 3],
            "nperiodic_dimensions": [3, 3],
            "chemical_formula_reduced": ["C4NiTm3", "Dy2MoO6"],
            "chemical_formula_descriptive": ["C4NiTm3", "Dy2MoO6"],
            "chemical_formula_anonymous": ["A4B3C", "A4B3C"],
            "elements": ["C-Ni-Tm", "Dy-Mo-O"],
            "energy": [-58.4, -62.4],
        }
    )
    findings = consistency.check(df, LEMAT_BULK.consistency_rules)
    flagged_fields = {f.field for f in findings}
    assert "nsites" in flagged_fields
    assert "chemical_formula_reduced" in flagged_fields
    assert {f.row_id for f in findings} == {0, 1}
    # energy is NOT in the rule, so its (expected) difference is never flagged.
    assert "energy" not in flagged_fields
