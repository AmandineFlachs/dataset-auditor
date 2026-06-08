"""Regenerate the committed LeMat-Bulk example report (examples/lemat_bulk_report.html).

The real LeMat-Bulk sample is honestly clean on the formula axis -- all 25k rows have
mutually-consistent formula columns -- so a report from untouched data never shows the
formula check doing anything. To make the example *demonstrate* that check, this script
plants a few deliberately-corrupted formula rows IN MEMORY (the data/ CSV is never
modified) and renders the report from that.

Everything else in the report is the genuine audit of the real sample. The only
synthetic findings are the handful of `formula.*` rows listed in PLANTED below; their
evidence shows the tampered values, and this script is the record of exactly what was
changed. Run:  python scripts/make_example_report.py
"""

from __future__ import annotations

from pathlib import Path

from auditor.checks import run_all
from auditor.datasets import get
from auditor.load import load
from auditor.report import write

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "examples" / "lemat_bulk_report.html"

# Each entry corrupts one real row's formula columns to exercise a different branch of
# checks/formula.py. (row index, {column: bad value}, what it demonstrates).
PLANTED = [
    (0, {"chemical_formula_anonymous": "A9B9"}, "anonymous count multiset disagrees with reduced"),
    (1, {"chemical_formula_descriptive": "Si1 O2"}, "descriptive composition disagrees with reduced"),
    (2, {"nelements": 99}, "nelements count contradicts the parsed composition"),
    (3, {"elements": "Xx-Yy-Zz"}, "elements list does not match the formula's element set"),
    (4, {"chemical_formula_reduced": "2Broken9"}, "reduced (the anchor) is unparseable -> warn"),
]


def main() -> None:
    spec = get("lemat_bulk")
    df = load(None, spec=spec)  # untouched real sample
    n_real = len(df)

    # Plant the synthetic formula defects in memory only.
    for idx, changes, why in PLANTED:
        for col, value in changes.items():
            df.at[df.index[idx], col] = value
        print(f"  planted row {idx}: {changes}  ({why})")

    findings = run_all(df, spec)
    n_formula = sum(f.check.startswith("formula.") for f in findings)
    path = write(
        findings,
        spec,
        OUT,
        df=df,
        n_rows=n_real,
        generated_at="2026-06-07 (example: real audit + planted formula defects)",
    )
    print(f"\n{len(findings):,} findings ({n_formula} synthetic formula.*) -> {path}")


if __name__ == "__main__":
    main()
