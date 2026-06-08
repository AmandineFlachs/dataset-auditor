"""Crafted-row tests for the near-duplicate (shared-content) check."""

import pandas as pd

from auditor.checks import near_dup
from auditor.datasets import LEMAT_BULK, NearDupRule


def test_same_content_different_identity_is_flagged():
    # One fingerprint, two different ids -> the same thing recorded twice.
    df = pd.DataFrame(
        {
            "row_id": [0, 1, 2],
            "fp": ["h1", "h1", "h2"],
            "uid": ["a", "b", "c"],
        }
    )
    rule = NearDupRule(content_key="fp", identity="uid")
    findings = near_dup.check(df, [rule])
    assert {f.row_id for f in findings} == {0, 1}
    assert all(f.check == "near_dup.shared_content" for f in findings)
    assert all(f.severity.value == "warn" for f in findings)
    assert "a" in findings[0].evidence and "b" in findings[0].evidence


def test_same_content_same_identity_is_not_flagged():
    # One id repeating under one fingerprint is the expected recurrence, not a dup.
    df = pd.DataFrame({"row_id": [0, 1], "fp": ["h1", "h1"], "uid": ["a", "a"]})
    rule = NearDupRule(content_key="fp", identity="uid")
    assert near_dup.check(df, [rule]) == []


def test_identity_none_flags_any_shared_content():
    df = pd.DataFrame({"row_id": [0, 1, 2], "fp": ["h1", "h1", "h2"]})
    rule = NearDupRule(content_key="fp", identity=None)
    findings = near_dup.check(df, [rule])
    assert {f.row_id for f in findings} == {0, 1}


def test_null_content_keys_do_not_group():
    # Two missing fingerprints are not "the same content".
    df = pd.DataFrame({"row_id": [0, 1], "fp": [None, None], "uid": ["a", "b"]})
    rule = NearDupRule(content_key="fp", identity="uid")
    assert near_dup.check(df, [rule]) == []


def test_unique_content_yields_nothing():
    df = pd.DataFrame({"row_id": [0, 1], "fp": ["h1", "h2"], "uid": ["a", "b"]})
    rule = NearDupRule(content_key="fp", identity="uid")
    assert near_dup.check(df, [rule]) == []


def test_missing_content_column_is_skipped():
    df = pd.DataFrame({"row_id": [0, 1], "uid": ["a", "b"]})
    rule = NearDupRule(content_key="absent", identity="uid")
    assert near_dup.check(df, [rule]) == []


def test_no_rules_yields_nothing():
    df = pd.DataFrame({"row_id": [0], "fp": ["h1"]})
    assert near_dup.check(df, []) == []


def test_real_lemat_rule_flags_one_structure_under_two_ids():
    # The shape seen in the real data: one entalpic_fingerprint, two provenance ids.
    df = pd.DataFrame(
        {
            "row_id": [0, 1],
            "entalpic_fingerprint": ["000d815ae_2_Ti1S4", "000d815ae_2_Ti1S4"],
            "immutable_id": ["oqmd-5612459", "oqmd-5604903"],
            "chemical_formula_reduced": ["Cl6S4Ti", "Cl6S4Ti"],
        }
    )
    findings = near_dup.check(df, LEMAT_BULK.near_dup_rules)
    assert {f.row_id for f in findings} == {0, 1}
    assert "oqmd-5612459" in findings[0].evidence
