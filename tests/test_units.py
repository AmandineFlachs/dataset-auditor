"""Crafted-bad-row tests for the units (range + null-island) check."""

import pandas as pd

from auditor.checks import units


def test_longitude_out_of_range():
    df = pd.DataFrame({"row_id": [0, 1], "reclat": [10.0, 0.0], "reclong": [354.47, 5.0]})
    flagged = [f for f in units.check(df) if f.field == "reclong"]
    assert len(flagged) == 1
    assert flagged[0].row_id == 0
    assert flagged[0].severity.value == "error"


def test_future_year_flagged():
    df = pd.DataFrame({"row_id": [0], "year": [2501.0]})
    assert any(f.field == "year" and f.row_id == 0 for f in units.check(df))


def test_zero_mass_flagged():
    df = pd.DataFrame({"row_id": [0, 1], "mass_g": [0.0, 5.0]})
    flagged = [f for f in units.check(df) if f.field == "mass_g"]
    assert len(flagged) == 1 and flagged[0].row_id == 0  # only the 0 g row


def test_null_island_flagged():
    df = pd.DataFrame({"row_id": [0, 1], "reclat": [0.0, 10.0], "reclong": [0.0, 20.0]})
    ni = [f for f in units.check(df) if f.check == "units.null_island"]
    assert len(ni) == 1 and ni[0].row_id == 0


def test_missing_value_is_not_a_range_violation():
    df = pd.DataFrame({"row_id": [0], "reclong": [float("nan")]})
    assert units.check(df) == []


def test_range_rule_on_non_numeric_column_does_not_crash():
    # A rule on an object-dtype column must coerce, not raise TypeError and abort.
    df = pd.DataFrame({"row_id": [0, 1], "year": ["1999", "abc"]})
    findings = units.check(df, rules={"year": {"max": 2025}}, null_island=False)
    assert findings == []  # 'abc' -> NaN (excluded); '1999' is in range
