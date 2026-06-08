"""Structural checks that work on ANY DataFrame — no domain knowledge needed.

For v1 this is the per-column null rate: which columns are missing so much data
that any analysis built on them is suspect. (Type-mismatch detection is a natural
extension; see ROADMAP.)
"""

from __future__ import annotations

import pandas as pd

from auditor.models import Finding, Severity

# Columns missing more than this fraction of their values get flagged.
NULL_RATE_THRESHOLD = 0.10  # 10%


def check(df: pd.DataFrame, threshold: float = NULL_RATE_THRESHOLD) -> list[Finding]:
    n = len(df)
    if n == 0:
        return []

    findings: list[Finding] = []
    for col in df.columns:
        if col == "row_id":  # our synthetic id is never missing
            continue
        null_rate = float(df[col].isna().mean())
        if null_rate > threshold:
            findings.append(
                Finding(
                    check="schema.high_null_rate",
                    severity=Severity.WARN,
                    row_id=None,  # dataset-level finding, not tied to one row
                    field=col,
                    message=f"Column {col!r} is {null_rate:.1%} null (over the {threshold:.0%} threshold).",
                    evidence=f"{int(df[col].isna().sum()):,} of {n:,} rows missing",
                    expected=f"at most {threshold:.0%} missing",
                    suggested_fix="Decide whether to impute, drop the column, or document the gap.",
                )
            )
    return findings
