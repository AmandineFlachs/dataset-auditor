"""Formula agreement: the three chemical-formula columns must describe one composition.

This is the project's one genuinely *materials-specific* check, and it stays an
opt-in domain pack: it runs only when a spec declares ``formula_rules`` (see
:class:`~auditor.datasets.FormulaRule`), and is silent for every other dataset. The
meteorite set never touches it.

A LeMat-Bulk row encodes the same composition three redundant ways (the OPTIMADE
standard):

* ``chemical_formula_descriptive`` — ``"Cd2 In1 P1"`` (space-separated, explicit counts)
* ``chemical_formula_reduced``     — ``"Cd2InP"``     (alphabetical, divided by the GCD, 1s dropped)
* ``chemical_formula_anonymous``   — ``"A2BC"``       (counts descending, GCD-reduced, elements anonymized)

Redundant encodings that disagree are an internal contradiction — a real ingest/
harmonization defect — so a genuine mismatch is an ``error``. Two more cross-checks
ride along when the spec names the columns: the ``elements`` list and the
``nelements`` count must match the parsed composition.

**Deliberately dependency-free.** These are machine-generated OPTIMADE strings with a
trivial, regular grammar (``[A-Z][a-z]?`` symbol + optional integer; no parentheses,
hydrates, or decimals), and the check compares the columns *against each other*, not
against external chemistry knowledge. So it needs symbol+count parsing and a GCD, not
a chemistry engine: a small stdlib parser is the right, honest tool, and it keeps the
domain pack as light as ``schema.py`` (no pymatgen subtree pulled into the core).

Like ``consistency.py`` it is honestly clean on the current sample — redundant columns
that already agree — so it exists to catch the defect the moment one appears; a
crafted-defect test proves it fires.
"""

from __future__ import annotations

import re
from functools import reduce
from math import gcd

import pandas as pd

from auditor.models import Finding, Severity

# One symbol (capital + optional single lowercase) and an optional integer count.
# Matches both real element symbols (Cd, In, P) and the anonymous A/B/C placeholders.
_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def check(df: pd.DataFrame, rules=()) -> list[Finding]:
    """Run every formula-agreement rule and concatenate the Findings."""
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(_apply(df, rule))
    return findings


def _apply(df: pd.DataFrame, rule) -> list[Finding]:
    # The check is anchored on the reduced column (the canonical composition); fall
    # back to descriptive if a spec only names that one. Without either there is
    # nothing to compare against, so the rule is a no-op.
    anchor_col = next((c for c in (rule.reduced, rule.descriptive) if c and c in df.columns), None)
    if anchor_col is None:
        return []

    findings: list[Finding] = []
    for row in df.itertuples(index=False):
        findings.extend(_check_row(row._asdict(), rule, anchor_col))
    return findings


def _check_row(row: dict, rule, anchor_col: str) -> list[Finding]:
    row_id = _row_id(row)
    anchor_raw = row.get(anchor_col)
    anchor = _parse(anchor_raw)
    if anchor is None:
        # Can't parse the reference composition -> can't verify anything for this row.
        # Surface it (a malformed canonical formula is itself a defect) and stop.
        if _present(anchor_raw):
            return [_unparseable(row_id, anchor_col, anchor_raw)]
        return []
    anchor = _reduce(anchor)

    out: list[Finding] = []

    # descriptive vs reduced: same elements, same reduced counts.
    if rule.descriptive and rule.descriptive != anchor_col and rule.descriptive in row:
        out += _compare_composition(row, rule.descriptive, anchor, anchor_col, row_id)

    # anonymous vs reduced: counts (identity-blind) must match the reduced count multiset.
    if rule.anonymous and rule.anonymous in row:
        out += _compare_anonymous(row, rule.anonymous, anchor, anchor_col, row_id)

    # elements list vs the parsed element set.
    if rule.elements and rule.elements in row:
        out += _compare_elements(row, rule.elements, anchor, anchor_col, row_id)

    # nelements count vs the number of distinct elements.
    if rule.nelements and rule.nelements in row:
        out += _compare_nelements(row, rule.nelements, anchor, anchor_col, row_id)

    return out


# -- individual comparisons ---------------------------------------------------


def _compare_composition(row, col, anchor, anchor_col, row_id) -> list[Finding]:
    raw = row.get(col)
    comp = _parse(raw)
    if comp is None:
        return [_unparseable(row_id, col, raw)] if _present(raw) else []
    if _reduce(comp) != anchor:
        return [_mismatch(row_id, col, f"{col}={raw!r} vs {anchor_col} composition {_fmt(anchor)}",
                          f"{_fmt(anchor)} (matching {anchor_col})")]
    return []


def _compare_anonymous(row, col, anchor, anchor_col, row_id) -> list[Finding]:
    raw = row.get(col)
    anon = _parse(raw)
    if anon is None:
        return [_unparseable(row_id, col, raw)] if _present(raw) else []
    # Anonymous drops element identity, so compare only the multiset of counts.
    if sorted(anon.values(), reverse=True) != sorted(anchor.values(), reverse=True):
        return [_mismatch(row_id, col, f"{col}={raw!r} vs {anchor_col} counts {sorted(anchor.values(), reverse=True)}",
                          f"counts {sorted(anchor.values(), reverse=True)} (matching {anchor_col})")]
    return []


def _compare_elements(row, col, anchor, anchor_col, row_id) -> list[Finding]:
    raw = row.get(col)
    if not _present(raw):
        return []
    listed = {tok for tok in re.split(r"[-,\s]+", str(raw).strip()) if tok}
    if listed != set(anchor):
        return [_mismatch(row_id, col, f"{col}={raw!r} vs elements in {anchor_col} {sorted(anchor)}",
                          f"elements {sorted(anchor)} (from {anchor_col})")]
    return []


def _compare_nelements(row, col, anchor, anchor_col, row_id) -> list[Finding]:
    raw = row.get(col)
    if not _present(raw):
        return []
    try:
        declared = int(raw)
    except (TypeError, ValueError):
        return []
    if declared != len(anchor):
        return [_mismatch(row_id, col, f"{col}={declared} but {anchor_col} has {len(anchor)} distinct elements",
                          f"{len(anchor)} distinct elements (per {anchor_col})")]
    return []


# -- parsing ------------------------------------------------------------------


def _parse(formula) -> dict[str, int] | None:
    """Parse ``"Cd2 In1 P1"`` / ``"Cd2InP"`` / ``"A2BC"`` -> ``{El: count}``.

    Returns ``None`` if the string is empty/missing or contains anything the simple
    OPTIMADE grammar does not cover (so the caller can flag it as unparseable rather
    than silently mis-comparing).
    """
    if not _present(formula):
        return None
    compact = str(formula).replace(" ", "")
    if not compact:
        return None
    comp: dict[str, int] = {}
    i = 0
    while i < len(compact):
        m = _TOKEN.match(compact, i)
        if m is None or m.start() != i or not m.group(1):
            return None  # a stray token (digit-first, lone lowercase, symbol) -> unparseable
        comp[m.group(1)] = comp.get(m.group(1), 0) + (int(m.group(2)) if m.group(2) else 1)
        i = m.end()
    return comp or None


def _reduce(comp: dict[str, int]) -> dict[str, int]:
    """Divide counts by their GCD so e.g. ``Fe4O6`` compares equal to ``Fe2O3``."""
    g = reduce(gcd, comp.values())
    return {k: v // g for k, v in comp.items()} if g > 1 else dict(comp)


def _fmt(comp: dict[str, int]) -> str:
    return "".join(f"{el}{n}" for el, n in sorted(comp.items()))


# -- helpers ------------------------------------------------------------------


def _present(value) -> bool:
    """True if a cell holds an actual value (not NaN / None / empty)."""
    return value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip() != ""


def _row_id(row: dict):
    rid = row.get("row_id")
    try:
        return int(rid)
    except (TypeError, ValueError):
        return None


def _mismatch(row_id, field, evidence, expected) -> Finding:
    return Finding(
        check="formula.mismatch",
        severity=Severity.ERROR,
        row_id=row_id,
        field=field,
        message=(
            "Chemical-formula columns disagree: these are redundant encodings of one "
            "composition and must describe the same elements and proportions."
        ),
        evidence=evidence,
        expected=expected,
        suggested_fix="Recompute the formula representations from the structure so all columns agree.",
    )


def _unparseable(row_id, field, value) -> Finding:
    return Finding(
        check="formula.unparseable",
        severity=Severity.WARN,
        row_id=row_id,
        field=field,
        message="Could not parse this formula string, so its agreement with the other columns is unverified.",
        evidence=f"{field}={value!r}",
        suggested_fix="Check the formula encoding; expected element-symbol + count tokens (e.g. 'Cd2InP').",
    )
