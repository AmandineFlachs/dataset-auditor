"""Check modules + the registry that runs them.

Every check is a function with the same signature::

    def check(df: pd.DataFrame) -> list[Finding]

That uniform shape is the whole point: the runner below loops over checks
without knowing what any of them do, and the report (Phase 4) renders their
Findings generically. Adding a check = adding it to ``build_checks``; per-dataset
rules come from a ``DatasetSpec`` (see ``auditor.datasets``).
"""

from __future__ import annotations

from collections import Counter
from functools import partial
from typing import Callable

import pandas as pd

from auditor.datasets import DatasetSpec, get
from auditor.models import Finding
from auditor.checks import consistency, duplicates, formula, near_dup, pii, schema, units

# The "plug" type every check conforms to.
Check = Callable[[pd.DataFrame], list[Finding]]


def build_checks(spec: DatasetSpec, client=None) -> list[Check]:
    """Build the check list bound to one dataset's rules.

    Each entry is still a plain ``Callable[[df], list[Finding]]`` — the uniform
    contract the runner and report rely on — but ``units`` and ``duplicates`` are
    pre-fed this dataset's plausibility bounds, null-island flag, and key column
    via ``functools.partial``. ``schema`` needs no config (it is fully generic).
    Order is display order, nothing more.

    ``labels`` (the LLM-judged check) is appended only when a spec declares
    ``label_rules``, and imported lazily there, so the deterministic pipeline — and a
    bare ``import auditor.checks`` — never pulls in the HTTP client. ``client`` is the
    optional :class:`~auditor.llm.LLMClient` threaded through to it.
    """
    checks: list[Check] = [
        schema.check,
        partial(units.check, rules=spec.range_rules, null_island=spec.null_island),
        partial(duplicates.check, key=spec.key_column),
        partial(consistency.check, rules=spec.consistency_rules),
        partial(near_dup.check, rules=spec.near_dup_rules),
        partial(pii.check, columns=spec.pii_text_columns),
        partial(formula.check, rules=spec.formula_rules),
    ]
    if spec.label_rules:
        from auditor.checks import labels  # lazy: only the LLM check needs the client/httpx

        checks.append(
            partial(labels.check, rules=spec.label_rules, context=spec.domain_context, client=client)
        )
    return checks


def run_all(df: pd.DataFrame, spec: DatasetSpec | None = None, client=None) -> list[Finding]:
    """Run every check for ``spec`` (default: LeMat-Bulk) and concatenate Findings."""
    spec = spec or get()
    findings: list[Finding] = []
    for check in build_checks(spec, client=client):
        findings.extend(check(df))
    return findings


def _summarize(findings: list[Finding]) -> str:
    out = [f"total findings: {len(findings):,}"]

    by_sev = Counter(f.severity.value for f in findings)
    out.append("by severity: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())))

    out.append("by check:")
    for name, count in Counter(f.check for f in findings).most_common():
        out.append(f"  {name:<28} {count:>6,}")

    out.append("\none example per check:")
    seen: set[str] = set()
    for f in findings:
        if f.check in seen:
            continue
        seen.add(f.check)
        out.append(f"  [{f.severity.value:<5}] {f.check} | row={f.row_id} field={f.field} | {f.evidence}")
    return "\n".join(out)
