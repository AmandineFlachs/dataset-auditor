"""Loader + split-integrity tests for the benchmark cases. Model-free."""

import pytest

from shared import cases


def test_shipped_task_loads_and_is_balanced():
    meta = cases.load_meta("labels_plausibility")
    assert meta["column"] == "phase_at_stp"
    for split, n in meta["splits"].items():
        loaded = cases.load_split("labels_plausibility", split)
        assert len(loaded) == n
        pl = sum(1 for c in loaded if c["expected"] == "plausible")
        assert pl == n // 2  # balanced 50/50


def test_load_jsonl_skips_blanks_comments_and_warning(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(
        '\n// a comment\n{"_warning": "held out"}\n{"id": "a", "value": "v", "context": {}, "expected": "plausible"}\n',
        encoding="utf-8",
    )
    rows = cases.load_jsonl(p)
    assert len(rows) == 1 and rows[0]["id"] == "a"


def test_validate_cases_catches_problems():
    meta = {"allowed": ["solid", "liquid", "gas"], "expected_values": ["plausible", "implausible"]}
    bad = [
        {"id": "dup", "value": "solid", "context": {}, "expected": "plausible"},
        {"id": "dup", "value": "solid", "context": {}, "expected": "plausible"},  # duplicate id
        {"id": "badexp", "value": "solid", "context": {}, "expected": "maybe"},   # bad expected
        {"id": "badval", "value": "plasma", "context": {}, "expected": "plausible"},  # not in vocab
        {"id": "noctx", "value": "solid", "context": "oops", "expected": "plausible"},  # context not dict
    ]
    errors = cases.validate_cases(bad, meta)
    blob = " ".join(errors)
    assert "duplicate id" in blob and "maybe" in blob and "plasma" in blob and "context" in blob


def test_shipped_splits_are_disjoint():
    cases.assert_disjoint_splits("labels_plausibility")  # must not raise


def test_assert_disjoint_splits_raises_on_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_ROOT", tmp_path)
    task = tmp_path / "toy"
    task.mkdir()
    line = '{{"id": "{i}", "value": "solid", "context": {{"e": "X"}}, "expected": "plausible"}}'
    (task / "dev.jsonl").write_text(line.format(i="shared") + "\n", encoding="utf-8")
    (task / "test.jsonl").write_text(line.format(i="shared") + "\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        cases.assert_disjoint_splits("toy")
