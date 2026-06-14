"""Readiness rubric tests. Pure: synthetic Finding lists, no model."""

from auditor import rubric
from auditor.datasets import get
from auditor.models import Finding, Severity

# The exact set of deterministic check ids run_all can emit. If a check adds/renames an id,
# this test fails until DIMENSIONS is updated — so no check can silently go unscored.
KNOWN_DETERMINISTIC_IDS = {
    "schema.high_null_rate",
    "units.out_of_range", "units.null_island",
    "duplicates.exact_row", "duplicates.duplicate_key",
    "consistency.group_mismatch", "consistency.value_spread",
    "near_dup.shared_content",
    "pii.email", "pii.ssn", "pii.credit_card", "pii.phone", "pii.ipv4",
    "formula.mismatch", "formula.unparseable",
}


def test_every_deterministic_check_id_is_mapped_exactly_once():
    assert set(rubric._ID_TO_DIM) == KNOWN_DETERMINISTIC_IDS


def test_clean_dataset_scores_100():
    r = rubric.score([], n_rows=100)
    assert r.readiness == 100.0
    assert all(d.score == 100.0 for d in r.dimensions)


def test_severity_weighting_and_row_fraction():
    findings = [
        Finding(check="units.out_of_range", severity=Severity.ERROR, row_id=1, field="x", message="m"),
        Finding(check="units.out_of_range", severity=Severity.WARN, row_id=2, field="x", message="m"),
    ]
    r = rubric.score(findings, n_rows=100)
    plaus = next(d for d in r.dimensions if d.name == "plausibility")
    # one error row (1.0) + one warn row (0.5) = 1.5 weighted of 100 -> 98.5
    assert plaus.weighted_affected == 1.5
    assert plaus.score == 98.5
    assert plaus.affected_rows == 2


def test_dataset_level_finding_applies_flat_penalty():
    findings = [Finding(check="schema.high_null_rate", severity=Severity.WARN, row_id=None, field="y", message="40% null")]
    r = rubric.score(findings, n_rows=100)
    completeness = next(d for d in r.dimensions if d.name == "completeness")
    assert completeness.score == 95.0  # 100 - one 5-point dataset penalty


def test_labels_are_advisory_only_and_do_not_move_the_score():
    findings = [Finding(check="labels.implausible", severity=Severity.WARN, row_id=7, field="cat", message="?")]
    r = rubric.score(findings, n_rows=100)
    plaus = next(d for d in r.dimensions if d.name == "plausibility")
    assert plaus.score == 100.0                      # not moved by the label finding
    assert plaus.advisory == {"labels_flagged_rows": 1, "note": rubric._advisory_for(findings)["note"]}
    assert r.readiness == 100.0


def test_not_assessed_dimensions_are_none_and_excluded_from_readiness():
    r = rubric.score([], n_rows=100, not_assessed=("privacy", "consistency"))
    privacy = next(d for d in r.dimensions if d.name == "privacy")
    assert privacy.score is None and privacy.assessed is False
    # readiness is the mean of only the assessed dimensions (all 100 here)
    assert r.readiness == 100.0


def test_unassessed_dimensions_from_spec():
    for name in ("meteorites", "lemat_bulk"):
        na = rubric.unassessed_dimensions(get(name))
        assert isinstance(na, tuple)
        # schema + duplicates always run, so these are never "not assessed"
        assert "completeness" not in na and "duplication" not in na


def test_privacy_assessed_when_text_columns_present():
    import pandas as pd

    # PII auto-scans, so privacy is assessed whenever there's text to scan, and only
    # unassessed on a purely numeric frame.
    spec = get("meteorites")  # declares no pii_text_columns
    with_text = pd.DataFrame({"row_id": [0], "name": ["Aachen"]})
    numeric_only = pd.DataFrame({"row_id": [0], "mass_g": [1.0]})
    assert "privacy" not in rubric.unassessed_dimensions(spec, with_text)
    assert "privacy" in rubric.unassessed_dimensions(spec, numeric_only)
