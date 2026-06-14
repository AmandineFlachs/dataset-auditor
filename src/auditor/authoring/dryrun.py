"""Dry-run a candidate rule against the REAL check, in isolation.

The reuse insight that makes authoring cheap: every check already accepts a single rule, so
a proposal can be tried for real without new machinery. Each candidate kind maps to its
check (``units`` / ``duplicates`` / ``consistency`` / ``near_dup`` / ``formula``); the
returned ``Finding``s are summarized into the evidence a human (or the auto policy) decides
on. The evidence is exactly what would happen if the rule shipped -- no simulation, no drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from auditor.authoring.proposals import Candidate
from auditor.checks import consistency, duplicates, formula, near_dup, units
from auditor.models import Finding

# A few real flagged values, enough to characterize the rule without dumping every row.
_MAX_SAMPLES = 3


@dataclass(frozen=True)
class Evidence:
    """What dry-running a candidate would flag on the actual data."""

    flag_count: int
    flag_rate: float  # flagged rows / total rows, in [0, 1]
    samples: list[str] = field(default_factory=list)


def _findings(candidate: Candidate, df: pd.DataFrame) -> list[Finding]:
    """Run the candidate's matching check on a one-rule fragment, in isolation."""
    kind = candidate.kind
    if kind == "range":
        return units.check(df, rules={candidate.column: candidate.range_params()}, null_island=False)
    if kind == "key":
        # duplicates.check returns exact-row dupes too; keep only the key-uniqueness signal.
        return [f for f in duplicates.check(df, key=candidate.column)
                if f.check == "duplicates.duplicate_key"]
    if kind == "consistency":
        return consistency.check(df, rules=(candidate.to_rule(),))
    if kind == "near_dup":
        return near_dup.check(df, rules=(candidate.to_rule(),))
    if kind == "formula":
        return formula.check(df, rules=(candidate.to_rule(),))
    raise ValueError(f"dry_run does not support kind={kind!r}")


def dry_run(candidate: Candidate, df: pd.DataFrame) -> Evidence:
    """Run ``candidate`` through its matching check and summarize the findings."""
    findings = _findings(candidate, df)
    total = len(df) or 1
    samples = [f.evidence for f in findings[:_MAX_SAMPLES] if f.evidence]
    return Evidence(flag_count=len(findings), flag_rate=len(findings) / total, samples=samples)
