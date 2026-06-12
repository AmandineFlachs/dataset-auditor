"""Dry-run a candidate rule against the REAL check, in isolation.

The reuse insight that makes authoring cheap: every check already accepts a single rule,
so a proposal can be tried for real without new machinery. A range candidate becomes a
one-rule fragment fed to ``units.check``; the returned ``Finding``s are summarized into
the evidence a human (or the auto policy) decides on. The evidence is exactly what would
happen if the rule shipped -- no simulation, no drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from auditor.authoring.proposals import Candidate
from auditor.checks import units

# A few real flagged values, enough to characterize the rule without dumping every row.
_MAX_SAMPLES = 3


@dataclass(frozen=True)
class Evidence:
    """What dry-running a candidate would flag on the actual data."""

    flag_count: int
    flag_rate: float  # flagged rows / total rows, in [0, 1]
    samples: list[str] = field(default_factory=list)


def dry_run(candidate: Candidate, df: pd.DataFrame) -> Evidence:
    """Run ``candidate`` through its matching check and summarize the findings.

    Slice 1 handles ``kind="range"`` via ``units.check`` with ``null_island=False`` (the
    null-island check is multi-column and unrelated to a single range rule).
    """
    if candidate.kind != "range":
        raise ValueError(f"dry_run slice 1 supports kind='range', not {candidate.kind!r}")
    findings = units.check(df, rules={candidate.column: candidate.params()}, null_island=False)
    total = len(df) or 1
    samples = [f.evidence for f in findings[:_MAX_SAMPLES] if f.evidence]
    return Evidence(flag_count=len(findings), flag_rate=len(findings) / total, samples=samples)
