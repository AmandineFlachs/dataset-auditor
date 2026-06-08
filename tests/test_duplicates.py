"""Crafted-bad-row tests for the duplicates check."""

import pandas as pd

from auditor.checks import duplicates


def test_exact_duplicate_row_detected():
    # No 'id' column, so only the whole-row check is active.
    df = pd.DataFrame({"row_id": [0, 1, 2], "name": ["A", "B", "A"], "mass_g": [10.0, 20.0, 10.0]})
    findings = duplicates.check(df)
    flagged = [(f.check, f.row_id) for f in findings]
    assert ("duplicates.exact_row", 2) in flagged  # row 2 duplicates row 0
    assert all(f.check != "duplicates.duplicate_key" for f in findings)


def test_duplicate_key_detected():
    df = pd.DataFrame({"row_id": [0, 1, 2], "id": [5, 5, 7], "name": ["A", "B", "C"]})
    key_findings = [f for f in duplicates.check(df) if f.check == "duplicates.duplicate_key"]
    assert {f.row_id for f in key_findings} == {0, 1}  # both rows sharing id=5
    assert all(f.severity.value == "error" for f in key_findings)


def test_clean_data_yields_nothing():
    df = pd.DataFrame({"row_id": [0, 1], "id": [1, 2], "name": ["A", "B"]})
    assert duplicates.check(df) == []


def test_missing_keys_not_flagged_as_duplicates():
    # Two rows that merely LACK an id are missing, not colliding (schema's concern).
    df = pd.DataFrame({"row_id": [0, 1, 2], "id": [None, None, 5]})
    key_findings = [f for f in duplicates.check(df, key="id") if f.check == "duplicates.duplicate_key"]
    assert key_findings == []


def test_explicit_key_none_disables_key_check():
    # An explicit None means "no unique key" -> disabled, even if an 'id' column exists.
    df = pd.DataFrame({"row_id": [0, 1], "id": [5, 5]})
    findings = duplicates.check(df, key=None)
    assert all(f.check != "duplicates.duplicate_key" for f in findings)
