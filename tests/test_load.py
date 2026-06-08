"""Tests for load(). They run on a tiny in-memory CSV — no network, no 45k rows.

The most important test here is `test_load_preserves_the_mess`: it locks in the
core principle that loading must NOT clean bad values.
"""

import io

from auditor.datasets import METEORITES
from auditor.load import load

# A 3-row sample that mirrors the real schema and deliberately includes two
# known problems: a future year (2101) and null-island coordinates (0, 0).
SAMPLE = (
    "name,id,nametype,recclass,mass,fall,year,reclat,reclong,GeoLocation\n"
    'Aachen,1,Valid,L5,21,Fell,1880,50.775,6.08333,"(50.775, 6.08333)"\n'
    'FromFuture,2,Valid,H6,720,Found,2101,0.0,0.0,"(0.0, 0.0)"\n'
    'Abee,6,Valid,EH4,107000,Fell,1952,54.2,-113.0,"(54.2, -113.0)"\n'
)


def _df():
    # Name the meteorite spec explicitly: these assertions validate meteorite
    # normalization (mass->mass_g, numeric coercion), independent of which dataset
    # is the global default.
    return load(io.StringIO(SAMPLE), spec=METEORITES)


def test_adds_sequential_row_id():
    assert list(_df()["row_id"]) == [0, 1, 2]


def test_columns_normalized_and_mass_renamed():
    df = _df()
    assert "mass_g" in df.columns  # unit encoded in the name
    assert "mass" not in df.columns
    assert all(c == c.lower() for c in df.columns)


def test_numeric_columns_are_numeric():
    df = _df()
    assert df["year"].dtype.kind in "if"  # int or float
    assert df["mass_g"].dtype.kind in "if"


def test_load_preserves_the_mess():
    """load() must NOT sanitize — the bad values are the findings."""
    df = _df()
    assert (df["year"] == 2101).any()  # future year survives
    assert ((df["reclat"] == 0) & (df["reclong"] == 0)).any()  # null-island survives


def test_column_collision_raises_clear_error():
    import pytest

    # 'Mass' and 'mass' both normalize to 'mass' -> a clear ValueError, not a cryptic
    # TypeError from passing a 2-column DataFrame to pd.to_numeric.
    csv = "Mass,mass,id\n1,2,7\n"
    with pytest.raises(ValueError, match="collision"):
        load(io.StringIO(csv), spec=METEORITES)
