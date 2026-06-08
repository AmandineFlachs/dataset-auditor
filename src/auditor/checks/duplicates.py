"""Exact-duplicate detection. Fully generic — works on any DataFrame.

Two kinds of exact duplication:
  * whole-row duplicates (every value identical), and
  * duplicate *keys* (a column that is supposed to be unique repeats).

Near-duplicate detection (semantically similar but not identical) needs
embeddings and lives in Phase 3, not here.
"""

from __future__ import annotations

import pandas as pd

from auditor.datasets import METEORITES
from auditor.models import Finding, Severity

# Bare-call default = the meteorite spec's key ("id"). The pipeline passes each
# dataset's own key explicitly via build_checks; this is just the direct-call
# fallback used by the meteorite-spec tests. Independent of datasets.DEFAULT.
KEY_COLUMN = METEORITES.key_column

# Sentinel: distinguishes "no key argument passed" (bare calls / the meteorite-spec
# tests, which fall back to KEY_COLUMN) from an explicit key=None, which the pipeline
# sends for a dataset whose spec sets key_column=None and which MUST disable the key
# check rather than silently reuse an unrelated dataset's key.
_UNSET = object()

# Columns that, if present, make a human-readable label for a flagged row.
_LABEL_COLUMNS = ("name", "id", "immutable_id", "chemical_formula_descriptive")


def check(df: pd.DataFrame, key=_UNSET) -> list[Finding]:
    # Only a *missing* argument falls back to the meteorite key. An explicit None means
    # "this dataset has no unique key" and disables the key check (see _duplicate_keys),
    # rather than silently reusing an unrelated dataset's key.
    if key is _UNSET:
        key = KEY_COLUMN
    return _exact_duplicate_rows(df) + _duplicate_keys(df, key)


def _exact_duplicate_rows(df: pd.DataFrame) -> list[Finding]:
    # Compare every column except our synthetic row_id (which is unique by design).
    cols = [c for c in df.columns if c != "row_id"]
    if not cols:
        return []
    # keep="first": flag only the 2nd+ occurrence, not the original.
    dup_mask = df.duplicated(subset=cols, keep="first")

    findings: list[Finding] = []
    for _, row in df.loc[dup_mask].iterrows():
        evidence = ", ".join(f"{c}={row[c]}" for c in _LABEL_COLUMNS if c in df.columns)
        findings.append(
            Finding(
                check="duplicates.exact_row",
                severity=Severity.WARN,
                row_id=int(row["row_id"]),
                field=None,
                message="Row is an exact duplicate of an earlier row.",
                evidence=evidence or None,
                expected="a unique row (no exact duplicate)",
                suggested_fix="Drop the duplicate, or confirm it is a legitimate repeated observation.",
            )
        )
    return findings


def _duplicate_keys(df: pd.DataFrame, key: str | None) -> list[Finding]:
    if key is None or key not in df.columns:
        return []
    # keep=False: flag *all* rows that share a duplicated key, so each colliding
    # record is reported (not just the later ones). The notna() guard excludes rows
    # whose key is simply MISSING: pandas treats all NaNs as equal, but a row that
    # lacks an id is the schema check's concern (high_null_rate), not a duplicate.
    dup_mask = df.duplicated(subset=[key], keep=False) & df[key].notna()

    findings: list[Finding] = []
    for _, row in df.loc[dup_mask].iterrows():
        findings.append(
            Finding(
                check="duplicates.duplicate_key",
                severity=Severity.ERROR,
                row_id=int(row["row_id"]),
                field=key,
                message=f"Duplicate {key!r} value; this column is expected to be unique.",
                evidence=f"{key}={row[key]}",
                expected=f"a unique {key} value",
                suggested_fix="Investigate why the identifier repeats; keys must be unique.",
            )
        )
    return findings
