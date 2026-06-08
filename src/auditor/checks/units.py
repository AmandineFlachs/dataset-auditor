"""Plausibility checks driven by a small, dataset-specific rules table.

The *engine* (loop over rules, flag out-of-range rows) is generic. The
*RANGE_RULES* are meteorite domain knowledge kept as data, not buried in
if/else branches. In a multi-dataset future these would come from a config file
(see ROADMAP) — the in-code dict is the right altitude for v1.

Note: detecting mixed unit *strings* (e.g. "5 kg" vs "5000 g") is also part of
the original plan, but meteorite mass is uniformly grams — there is no drift to
find here, so that detector is deferred (see ROADMAP) rather than shipped empty.
"""

from __future__ import annotations

import pandas as pd

from auditor.datasets import METEORITES
from auditor.models import Finding, Severity

# Bare-call default = the meteorite spec's rules (it is the proving ground that
# actually exercises this check). The pipeline never relies on this: build_checks
# passes each dataset's own rules explicitly. Independent of datasets.DEFAULT.
RANGE_RULES: dict[str, dict] = METEORITES.range_rules


def check(
    df: pd.DataFrame,
    rules: dict | None = None,
    null_island: bool = True,
) -> list[Finding]:
    rules = RANGE_RULES if rules is None else rules
    findings = _range_violations(df, rules)
    if null_island:
        findings += _null_island(df)
    return findings


def _describe_bounds(lo, hi, excl_min: bool, excl_max: bool) -> str:
    left = "(-inf" if lo is None else (f"({lo}" if excl_min else f"[{lo}")
    right = "inf)" if hi is None else (f"{hi})" if excl_max else f"{hi}]")
    return f"{left}, {right}"


def _range_violations(df: pd.DataFrame, rules: dict) -> list[Finding]:
    findings: list[Finding] = []
    for col, rule in rules.items():
        if col not in df.columns:
            continue
        # Coerce defensively: a range rule may name a column the spec did not list in
        # numeric_columns, so it can still be object dtype. to_numeric(errors="coerce")
        # turns a non-numeric cell into NaN (excluded by the notna mask below) instead
        # of raising TypeError on the comparison and aborting the whole audit.
        s = pd.to_numeric(df[col], errors="coerce")
        lo, hi = rule.get("min"), rule.get("max")
        excl_min, excl_max = rule.get("exclusive_min", False), rule.get("exclusive_max", False)

        mask = pd.Series(False, index=df.index)
        if lo is not None:
            mask |= (s <= lo) if excl_min else (s < lo)
        if hi is not None:
            mask |= (s >= hi) if excl_max else (s > hi)
        mask &= s.notna()  # missing values are schema's job, not a range error

        bounds = _describe_bounds(lo, hi, excl_min, excl_max)
        for _, row in df.loc[mask].iterrows():
            findings.append(
                Finding(
                    check="units.out_of_range",
                    severity=Severity.ERROR,
                    row_id=int(row["row_id"]),
                    field=col,
                    message=f"{col} is outside its plausible range {bounds}.",
                    evidence=f"{col}={row[col]}",
                    expected=f"within {bounds}",
                    suggested_fix="Likely a data-entry error; verify against the source record.",
                )
            )
    return findings


def _null_island(df: pd.DataFrame) -> list[Finding]:
    """Coordinates of exactly (0, 0) are a missing-location placeholder, not a
    real site in the Gulf of Guinea. A multi-column check, unlike the range rules.
    """
    if not {"reclat", "reclong"}.issubset(df.columns):
        return []
    mask = (df["reclat"] == 0) & (df["reclong"] == 0)

    findings: list[Finding] = []
    for row_id in df.loc[mask, "row_id"]:
        findings.append(
            Finding(
                check="units.null_island",
                severity=Severity.WARN,
                row_id=int(row_id),
                field="reclat+reclong",
                message="Coordinates are exactly (0, 0) - a placeholder for unknown location, not a real site.",
                evidence="(reclat, reclong) = (0.0, 0.0)",
                expected="a real recovered location, not (0, 0)",
                suggested_fix="Treat as a missing location rather than a Gulf-of-Guinea landing.",
            )
        )
    return findings
