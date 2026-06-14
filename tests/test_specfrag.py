"""Tests for loading an authored rule fragment and overlaying it onto a spec.

Closes the authoring loop: a fragment from `auditor author` becomes a spec the audit uses.
Model-free -- it execs a fragment and runs the deterministic checks, no LLM.
"""

import pandas as pd

from auditor.authoring.session import emit_fragment
from auditor.authoring.proposals import Candidate
from auditor.checks import run_all
from auditor.datasets import DatasetSpec
from auditor.specfrag import apply_fragment, load_fragment


def _base_spec() -> DatasetSpec:
    return DatasetSpec(name="t", filename="t.csv", numeric_columns=("val",))


def _frag_path(tmp_path, accepted):
    p = tmp_path / "authored.py"
    p.write_text(emit_fragment(accepted, "t"), encoding="utf-8")
    return p


def test_load_fragment_reads_range_and_dataclass_rules(tmp_path):
    accepted = [
        Candidate(kind="range", column="val", min=0, exclusive_min=True, rationale="r", confidence=0.9),
        Candidate(kind="consistency", group_by="gid", columns=["a"], rationale="r", confidence=0.9),
    ]
    fields = load_fragment(_frag_path(tmp_path, accepted))
    assert fields["range_rules"] == {"val": {"min": 0.0, "exclusive_min": True}}
    assert fields["consistency_rules"][0].group_by == "gid"  # the import-bearing fragment execs


def test_apply_fragment_overlays_only_rule_fields(tmp_path):
    base = _base_spec()
    spec2 = apply_fragment(base, {"range_rules": {"val": {"min": 0}}})
    assert spec2.range_rules == {"val": {"min": 0}}
    assert spec2.name == base.name and spec2.numeric_columns == base.numeric_columns  # identity intact
    assert base.range_rules == {}  # original is untouched (frozen replace)


def test_apply_empty_fragment_returns_spec_unchanged():
    base = _base_spec()
    assert apply_fragment(base, {}) is base


def test_authored_rules_drive_a_real_audit(tmp_path):
    # End to end: author -> fragment file -> overlay -> run_all fires the authored rule.
    accepted = [Candidate(kind="range", column="val", min=0, exclusive_min=True, rationale="r", confidence=0.9)]
    fields = load_fragment(_frag_path(tmp_path, accepted))
    spec = apply_fragment(_base_spec(), fields)
    df = pd.DataFrame({"row_id": [0, 1, 2], "val": [5.0, 0.0, -3.0]})  # rows 1,2 violate val>0
    findings = run_all(df, spec)
    bad = [f for f in findings if f.check == "units.out_of_range" and f.field == "val"]
    assert len(bad) == 2  # exactly the authored bound's predicted flags
