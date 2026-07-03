"""Config-driven multi-dataset path: load + checks honour a DatasetSpec.

Like the other tests these run on a tiny in-memory CSV — no network, no data
files — so they validate the *generalization*, not the bundled sample.
"""

import io

from auditor.checks import run_all
from auditor.datasets import LEMAT_BULK, METEORITES, TABLE_TRACES, get
from auditor.load import load

# LeMat-like rows: two share an immutable_id (duplicate key), dos_ef is mostly
# null (schema), and reclat/reclong are (0,0) — which must NOT trigger null-island
# because the LeMat spec disables it (the flag, not column presence, is the gate).
LEMAT_SAMPLE = (
    "immutable_id,nelements,nsites,nperiodic_dimensions,energy,dos_ef,functional,reclat,reclong\n"
    "mp-1,2,4,3,-10.5,1.2,pbe,0.0,0.0\n"
    "mp-1,2,4,3,-10.6,,pbesol,0.0,0.0\n"
    "mp-2,3,6,3,-20.1,,scan,0.0,0.0\n"
)


def _lemat_df():
    return load(io.StringIO(LEMAT_SAMPLE), spec=LEMAT_BULK)


# table_traces rows: the ML-training dataset onboarded as a third spec. row0/row1
# share example_id ex1 (duplicate key) AND base_table_id t1 with the same content
# sig AAA — the legitimate "same table, both orientations" case, which must NOT
# self-flag. row2 is a *different* base_table_id t2 carrying that same sig AAA, so
# the sig now spans two tables (a genuine cross-table near-dup); it also has
# n_cites=0, which violates the "a grounded trace cites >=1 cell" range rule.
TRACES_SAMPLE = (
    "example_id,base_table_id,table_content_sig,question_type,split,trace_source,"
    "difficulty,domain,question,answer_label,"
    "n_table_rows,n_table_cols,n_trace_steps,n_cites,answer_n_rows\n"
    "ex1,t1,AAA,best_under_constraint,train,programmatic,easy,finance,Q1,Energy,12,4,3,3,1\n"
    "ex1,t1,AAA,threshold_filter,eval,programmatic,easy,finance,Q2,Automotive,12,4,3,2,1\n"
    "ex2,t2,AAA,tradeoff_summary,train,programmatic,hard,finance,Q3,none,9,3,3,0,0\n"
)


def _traces_df():
    return load(io.StringIO(TRACES_SAMPLE), spec=TABLE_TRACES)


def test_get_defaults_to_lemat_bulk():
    assert get() is LEMAT_BULK            # flagship is the default
    assert get("meteorites") is METEORITES  # proving ground still addressable
    assert get("table_traces") is TABLE_TRACES  # ML-training dataset onboarded


def test_unknown_dataset_is_rejected():
    import pytest

    with pytest.raises(SystemExit):
        get("does_not_exist")


def test_lemat_numeric_coercion_and_row_id():
    df = _lemat_df()
    assert list(df["row_id"]) == [0, 1, 2]
    assert df["dos_ef"].dtype.kind == "f"  # coerced; blank cells -> NaN
    assert df["dos_ef"].isna().sum() == 2


def test_lemat_duplicate_immutable_id_flagged():
    findings = run_all(_lemat_df(), LEMAT_BULK)
    dup = [f for f in findings if f.check == "duplicates.duplicate_key"]
    assert {f.row_id for f in dup} == {0, 1}  # both rows sharing mp-1
    assert all(f.field == "immutable_id" for f in dup)


def test_lemat_high_null_dos_ef_flagged():
    findings = run_all(_lemat_df(), LEMAT_BULK)
    schema = [f for f in findings if f.check == "schema.high_null_rate"]
    assert any(f.field == "dos_ef" for f in schema)


def test_lemat_spec_disables_null_island():
    """(0,0) coords are present, but the LeMat spec must not run null-island."""
    findings = run_all(_lemat_df(), LEMAT_BULK)
    assert all(f.check != "units.null_island" for f in findings)


def test_traces_duplicate_example_id_flagged():
    findings = run_all(_traces_df(), TABLE_TRACES)
    dup = [f for f in findings if f.check == "duplicates.duplicate_key"]
    assert {f.row_id for f in dup} == {0, 1}  # both rows sharing ex1
    assert all(f.field == "example_id" for f in dup)


def test_traces_cross_table_near_dup_flagged():
    """Sig AAA spans base tables t1 and t2 — a genuine cross-table duplicate."""
    findings = run_all(_traces_df(), TABLE_TRACES)
    nd = [f for f in findings if f.check == "near_dup.shared_content"]
    assert nd and all(f.field == "table_content_sig" for f in nd)


def test_traces_ungrounded_trace_flagged_by_range():
    """n_cites=0 violates the 'a grounded trace cites >=1 cell' bound."""
    findings = run_all(_traces_df(), TABLE_TRACES)
    rng = [f for f in findings if f.check == "units.out_of_range" and f.field == "n_cites"]
    assert {f.row_id for f in rng} == {2}
