"""Structural guards run over EVERY shipped benchmark task. Model-free.

Adding a task automatically subjects its case files to the same gates (disjoint splits,
no leakage, valid ground truth, balanced classes, a matching frozen-prompt hash), so a
malformed or leaky task fails CI.
"""

import pytest

from shared import cases, freeze, leakage

TASKS = ["labels_plausibility", "element_classification"]


def _all_cases(task):
    out = []
    for split in cases.SPLITS:
        out += cases.load_split(task, split)
    return out


@pytest.mark.parametrize("task", TASKS)
def test_cases_valid(task):
    meta = cases.load_meta(task)
    assert cases.validate_cases(_all_cases(task), meta) == []


@pytest.mark.parametrize("task", TASKS)
def test_splits_disjoint(task):
    cases.assert_disjoint_splits(task)  # raises on overlap


@pytest.mark.parametrize("task", TASKS)
def test_no_leakage(task):
    rep = leakage.leakage_check(_all_cases(task), cases.load_meta(task))
    assert rep.ok, rep.summary()


@pytest.mark.parametrize("task", TASKS)
def test_classes_balanced_per_split(task):
    meta = cases.load_meta(task)
    for split, n in meta["splits"].items():
        cs = cases.load_split(task, split)
        assert len(cs) == n
        assert sum(1 for c in cs if c["expected"] == "plausible") == n // 2


@pytest.mark.parametrize("task", TASKS)
def test_frozen_prompt_matches(task):
    freeze.verify_frozen_prompt(task)  # raises FrozenPromptDrift if the prompt changed


@pytest.mark.parametrize("task", TASKS)
def test_value_label_decorrelated(task):
    """Every allowed value appears in BOTH classes, so 'guess by the word' can't win."""
    meta = cases.load_meta(task)
    allc = _all_cases(task)
    for val in meta["allowed"]:
        labels = {c["expected"] for c in allc if c["value"] == val}
        assert labels == {"plausible", "implausible"}, f"{task}: value {val!r} not in both classes"
