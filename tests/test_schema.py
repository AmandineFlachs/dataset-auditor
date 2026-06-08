"""Crafted-bad-row tests for the schema (null-rate) check."""

import pandas as pd

from auditor.checks import schema


def test_high_null_rate_flagged():
    df = pd.DataFrame({"row_id": [0, 1, 2, 3], "a": [1, None, None, None]})  # 75% null
    findings = schema.check(df)
    assert any(f.check == "schema.high_null_rate" and f.field == "a" for f in findings)


def test_below_threshold_not_flagged():
    df = pd.DataFrame({"row_id": [0, 1, 2, 3], "a": [1, 2, 3, None]})  # 25% null
    assert schema.check(df, threshold=0.5) == []


def test_row_id_is_never_flagged():
    df = pd.DataFrame({"row_id": [0, 1]})
    assert schema.check(df) == []


def test_strict_threshold_boundary():
    # null_rate > threshold is STRICT: exactly-at-threshold is NOT flagged, just-over is.
    at = pd.DataFrame({"row_id": list(range(10)), "x": [None] + list(range(9))})  # 10%
    assert all(f.field != "x" for f in schema.check(at))  # default threshold 0.10
    over = pd.DataFrame({"row_id": list(range(10)), "x": [None, None] + list(range(8))})  # 20%
    assert any(f.field == "x" for f in schema.check(over))
