"""Load a dataset into a normalized pandas DataFrame.

The guiding rule of this module: **normalize _structure_, never _content_.**

It is allowed to rename columns, add a stable ``row_id``, and coerce a column to
a numeric dtype. It is NOT allowed to delete rows, fill missing values, or
"correct" any value. The absurd entries (a year of 2101, ``(0, 0)`` coordinates,
mass outliers, duplicate material ids) MUST survive untouched — those are exactly
what the checks in later phases exist to find. If loading cleaned them away, the
tool would have nothing to report.

Dataset-specific knowledge (which columns are numeric, what to rename) lives in
``auditor.datasets`` as a :class:`~auditor.datasets.DatasetSpec`, not here. This
module is the generic engine; pass a different spec to load a different dataset.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

import pandas as pd

from auditor.datasets import DatasetSpec, get


def _normalize_columns(df: pd.DataFrame, rename_map: dict[str, str]) -> pd.DataFrame:
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    return df.rename(columns=rename_map)


def load(
    source: str | Path | IO | None = None,
    *,
    spec: DatasetSpec | None = None,
) -> pd.DataFrame:
    """Return the dataset as a normalized DataFrame with a stable ``row_id``.

    ``spec`` selects the dataset config (default: LeMat-Bulk). ``source`` overrides
    where the bytes come from — a path, URL, or any file-like object (so tests can
    pass a tiny in-memory CSV and run offline). When omitted, the spec's bundled
    ``data/<file>.csv`` is used.
    """
    spec = spec or get()
    if source is None:
        source = spec.path

    df = pd.read_csv(source)
    df = _normalize_columns(df, spec.rename_map)

    # Two source columns can collapse to one name after lower-casing (e.g. "Mass" and
    # "mass"), leaving duplicate labels; df[col] would then return a DataFrame and crash
    # the numeric coercion below with a cryptic TypeError. Fail loudly and specifically.
    collisions = df.columns[df.columns.duplicated()].unique().tolist()
    if collisions:
        raise ValueError(
            f"column-name collision after normalization: {collisions}. Two source "
            "columns map to the same name; rename one in the source data."
        )

    for col in spec.numeric_columns:
        if col in df.columns:
            # errors="coerce": a non-numeric cell becomes NaN (a *finding* for the
            # schema check) rather than crashing the load.
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # A fresh positional id, 0..n-1. We do NOT reuse the dataset's own key column
    # — it may have gaps or duplicates, which is itself something to detect later.
    # Every Finding needs an unambiguous location to point at.
    df.insert(0, "row_id", range(len(df)))
    return df


def profile(df: pd.DataFrame, spec: DatasetSpec | None = None) -> str:
    """Build a human-readable profile string.

    This is *exploratory*, not a check — it produces no Findings. Its job is to
    turn "I heard this data is messy" into "I can see the max year is 2101", so
    we form real hypotheses instead of guessing. It is dataset-agnostic: numeric
    columns are auto-detected, and ``spec.categorical_columns`` (if any) get
    value-counts.
    """
    spec = spec or get()
    data_cols = [c for c in df.columns if c != "row_id"]
    numeric = df[data_cols].select_dtypes("number").columns.tolist()

    out: list[str] = []
    out.append(f"dataset: {spec.name}")
    out.append(f"rows: {len(df):,}    columns: {len(data_cols)}")

    out.append("\ndtype & missing per column:")
    for col in data_cols:
        miss = df[col].isna().mean() * 100
        out.append(f"  {col:<28} {str(df[col].dtype):<10} {miss:5.1f}% missing")

    out.append("\nnumeric ranges (min / max / mean):")
    for col in numeric:
        s = df[col]
        out.append(
            f"  {col:<28} min={s.min():>14,.2f}  max={s.max():>14,.2f}  "
            f"mean={s.mean():>12,.2f}"
        )

    if spec.categorical_columns:
        out.append("\ncategoricals (value counts):")
        for col in spec.categorical_columns:
            if col in df.columns:
                out.append(f"  {col}: {df[col].value_counts(dropna=False).to_dict()}")

    # A few exploratory "smells" — NOT the real checks, just enough to confirm or
    # revise hypotheses before the detectors run. Each guards on column presence,
    # so this stays generic across datasets.
    out.append("\nquick smells (exploratory only):")
    if spec.key_column and spec.key_column in df.columns:
        dups = int(df[spec.key_column].duplicated().sum())
        out.append(f"  duplicate {spec.key_column!r} values:                {dups}")
    if {"reclat", "reclong"}.issubset(df.columns):
        null_island = int(((df["reclat"] == 0) & (df["reclong"] == 0)).sum())
        out.append(f"  rows at (0, 0) 'null island':              {null_island}")
    dup_cols = [c for c in df.columns if c != "row_id"]
    out.append(f"  exact duplicate rows (excl. row_id):       {int(df.duplicated(subset=dup_cols).sum())}")

    return "\n".join(out)


if __name__ == "__main__":
    import sys

    spec = get(sys.argv[1] if len(sys.argv) > 1 else None)
    df = load(spec=spec)
    print(profile(df, spec))
