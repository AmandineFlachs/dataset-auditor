"""Config-driven multi-dataset path: load + checks honour a DatasetSpec.

Like the other tests these run on a tiny in-memory CSV — no network, no data
files — so they validate the *generalization*, not the bundled sample.
"""

import io

from auditor.checks import run_all
from auditor.datasets import LEMAT_BULK, METEORITES, get
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


def test_get_defaults_to_lemat_bulk():
    assert get() is LEMAT_BULK            # flagship is the default
    assert get("meteorites") is METEORITES  # proving ground still addressable


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
