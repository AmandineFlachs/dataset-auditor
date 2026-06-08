"""Group-consistency: rows that share a key should agree with each other.

The generic idea, configured per dataset by a :class:`~auditor.datasets.ConsistencyRule`:
group the rows by some key, then within each group check that the columns which are
*supposed* to be the same actually are. It catches a class of bug the per-row checks
miss entirely — a problem that only shows up when you line two records up side by side.

Two modes (see :class:`~auditor.datasets.ConsistencyRule`):

* ``"exact"`` — the values must be identical. On LeMat-Bulk the same ``immutable_id``
  recurs once per DFT functional; whatever else differs, those rows describe the same
  material, so ``nsites``, the formulas, the element list must match exactly. A
  mismatch means two distinct structures were harmonized under one id.
* ``"numeric"`` — a numeric column must agree within a tolerance across the group,
  optionally per-unit (``normalize_by``). For quantities that should be close but may
  drift. Deliberately **not** used for DFT energies across functionals: those differ
  for sound physical reasons, so comparing them manufactures false positives.

Like every check, this is a generic engine. It owns no dataset knowledge; the rules
arrive from the spec. With no rules it returns nothing, so a dataset opts in simply by
declaring ``consistency_rules``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from auditor.models import Finding, Severity

# Columns that, if present, make a human-readable label for a flagged group.
_LABEL_COLUMNS = ("name", "immutable_id", "id", "functional")


def check(df: pd.DataFrame, rules=()) -> list[Finding]:
    """Run every consistency rule and concatenate the Findings."""
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(_apply(df, rule))
    return findings


def _apply(df: pd.DataFrame, rule) -> list[Finding]:
    if rule.group_by not in df.columns:
        return []
    cols = [c for c in rule.columns if c in df.columns]
    if not cols:
        return []

    findings: list[Finding] = []
    # Only groups with >1 row can be internally inconsistent; dropna=False so a
    # group keyed on a missing value is still examined rather than silently dropped.
    for _, group in df.groupby(rule.group_by, dropna=False):
        if len(group) < 2:
            continue
        if rule.mode == "numeric":
            findings.extend(_check_numeric(group, rule, cols))
        else:
            findings.extend(_check_exact(group, rule, cols))
    return findings


def _check_exact(group: pd.DataFrame, rule, cols: list[str]) -> list[Finding]:
    """Flag every row of a group whenever a supposedly-invariant column disagrees."""
    findings: list[Finding] = []
    key_label = _key_label(group, rule.group_by)
    for col in cols:
        # nunique(dropna=False) treats NaN as its own value, so "set in one row,
        # missing in another" correctly counts as a disagreement.
        if group[col].nunique(dropna=False) <= 1:
            continue
        values = sorted({_fmt(v) for v in group[col]})
        evidence = f"{key_label}: {col} differs across the group -> {{{', '.join(values)}}}"
        for row_id in group["row_id"]:
            findings.append(
                Finding(
                    check="consistency.group_mismatch",
                    severity=Severity.ERROR,
                    row_id=int(row_id),
                    field=col,
                    message=(
                        f"Rows sharing {rule.group_by}={_fmt(group[rule.group_by].iloc[0])} "
                        f"disagree on {col!r}, which should be identical for one entity."
                    ),
                    evidence=evidence,
                    expected=f"the same {col} for every row sharing {rule.group_by}",
                    suggested_fix="Investigate the merge: one identifier maps to conflicting records.",
                )
            )
    return findings


def _check_numeric(group: pd.DataFrame, rule, cols: list[str]) -> list[Finding]:
    """Flag a group whose numeric values spread beyond the allowed tolerance."""
    findings: list[Finding] = []
    key_label = _key_label(group, rule.group_by)
    for col in cols:
        values = pd.to_numeric(group[col], errors="coerce")
        if rule.normalize_by and rule.normalize_by in group.columns:
            denom = pd.to_numeric(group[rule.normalize_by], errors="coerce")
            values = values / denom
        # Keep only finite values: a zero denominator above yields +/-inf, which would
        # survive dropna() and make the spread inf, manufacturing a false finding.
        # Treat a zero/invalid divisor as missing instead (np.isfinite drops NaN too).
        values = values[np.isfinite(values)]
        if len(values) < 2:
            continue

        spread = float(values.max() - values.min())
        if rule.relative:
            # Relative to the group's typical magnitude; abs() so sign doesn't flip
            # the threshold, and a zero median degrades to an absolute-zero tolerance.
            scale = abs(float(values.median()))
            limit = rule.tolerance * scale
        else:
            limit = rule.tolerance
        if spread <= limit:
            continue

        unit = " per " + rule.normalize_by if rule.normalize_by else ""
        evidence = (
            f"{key_label}: {col}{unit} spans {values.min():.4g}..{values.max():.4g} "
            f"(spread {spread:.4g} > allowed {limit:.4g})"
        )
        for row_id in group["row_id"]:
            findings.append(
                Finding(
                    check="consistency.value_spread",
                    severity=Severity.WARN,
                    row_id=int(row_id),
                    field=col,
                    message=(
                        f"Rows sharing {rule.group_by}={_fmt(group[rule.group_by].iloc[0])} "
                        f"disagree on {col!r} beyond the allowed tolerance."
                    ),
                    evidence=evidence,
                    expected=f"{col} within tolerance across rows sharing {rule.group_by}",
                    suggested_fix="Check whether these records should share a key, or reconcile the values.",
                )
            )
    return findings


def _key_label(group: pd.DataFrame, group_by: str) -> str:
    """A short human label for a group, preferring known id/name columns."""
    for col in (group_by, *_LABEL_COLUMNS):
        if col in group.columns:
            return f"{col}={_fmt(group[col].iloc[0])}"
    return "group"


def _fmt(value) -> str:
    """Render a cell compactly, normalizing NaN to a readable token."""
    if pd.isna(value):
        return "<missing>"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
