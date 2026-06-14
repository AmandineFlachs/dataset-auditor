"""Render a list of ``Finding`` objects into one self-contained HTML report.

This is the payoff of the whole-pipeline contract (see ``models.py``): the report
reads ``Finding`` objects (plus, optionally, the audited DataFrame for context and
row-level drill-down) and knows nothing about any individual check. Add a check
tomorrow and it renders here for free.

What it does beyond "make HTML":

* **Aggregate identical findings.** A real audit produces thousands of findings that
  differ only by row id (6,214 meteorite rows all reading "(0, 0)"). Findings sharing
  a *signature* (field, message, evidence, fix, severity) collapse to one line with a
  count and sample row ids — the information, without the wall.
* **Group by check, most-severe first**, then **cap distinct rows** per check.
* **Drill down.** Each finding row expands in place to show the suggested fix, the
  full list of sample rows, and — when the DataFrame is supplied — the actual offending
  row's field values, so depth is one click away rather than a scroll to nowhere.
* **Sidebar context.** A sticky sidebar keeps the severity summary, search/filters, and
  a jump-to-check nav visible, plus an overview panel and a by-column cross-cut.

The output is a single file: inline CSS, a little inline JS, no external resources.
Evidence comes from the data, so the template autoescapes.

Run directly to audit a dataset and write a file::

    python -m auditor.report --dataset lemat_bulk --out report.html
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from auditor.datasets import DatasetSpec
from auditor.glossary import (
    SEV_CLASS,
    SEVERITY_LABEL,
    check_code,
    describe_check,
    severity_label,
)
from auditor.models import Finding, Severity
from auditor import rubric as rubric

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates"
TEMPLATE_NAME = "report.html.j2"

# Distinct (aggregated) rows shown per check before "+ N more distinct findings".
PER_CHECK_CAP = 50
# Sample row ids carried on an aggregated row (a few shown collapsed, all in drill-down).
MAX_SAMPLE_IDS = 12

# Display/ordering rank: most severe first.
_SEV_RANK = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}
_NO_FIELD = "(whole row / dataset)"


def _env() -> Environment:
    # autoescape is non-negotiable here: evidence is untrusted data, never markup.
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def render(
    findings: list[Finding],
    spec: DatasetSpec,
    *,
    df: pd.DataFrame | None = None,
    n_rows: int | None = None,
    generated_at: str = "",
    cap: int = PER_CHECK_CAP,
) -> str:
    """Return the report as an HTML string. Pass ``df`` for overview + drill-down."""
    if n_rows is None and df is not None:
        n_rows = len(df)
    indexed = df.set_index("row_id") if df is not None and "row_id" in df.columns else None
    groups = _grouped(findings, cap, indexed)
    overview = _overview(df, spec) if df is not None else None
    n_cols = overview["n_cols"] if overview else None
    readiness = rubric.score(findings, n_rows, not_assessed=rubric.unassessed_dimensions(spec, df))
    return _env().get_template(TEMPLATE_NAME).render(
        dataset=spec.name,
        file_name=spec.filename,
        source_url=spec.source_url,
        generated_at=generated_at,
        n_rows=n_rows,
        n_cols=n_cols,
        total=len(findings),
        stats=_stats(findings, n_rows),
        sev_counts=_severity_counts(findings),
        sev_labels=SEVERITY_LABEL,
        sev_class=SEV_CLASS,
        groups=groups,
        capped=any(g["hidden_rows"] for g in groups),
        cap=cap,
        field_summary=_field_summary(findings),
        overview=overview,
        readiness=readiness,
    )


def write(
    findings: list[Finding],
    spec: DatasetSpec,
    out_path: str | Path,
    **kwargs,
) -> Path:
    """Render and write the report to ``out_path``; return the path."""
    out_path = Path(out_path)
    out_path.write_text(render(findings, spec, **kwargs), encoding="utf-8")
    return out_path


def _severity_counts(findings: list[Finding]) -> list[tuple[str, int]]:
    """(severity, count) pairs in fixed error/warn/info order, omitting empties."""
    counts = Counter(f.severity for f in findings)
    return [(sev.value, counts[sev]) for sev in _SEV_RANK if counts.get(sev)]


def _stats(findings: list[Finding], n_rows: int | None) -> dict:
    """Headline numbers for the summary strip: totals by severity and the clean rate.

    ``rows_affected`` is the count of *distinct* source rows that carry at least one
    finding (dataset-level findings with no row_id don't count), so ``clean_pct`` is an
    honest 'how much of the data is untouched by any issue' figure."""
    by = Counter(f.severity for f in findings)
    affected = {f.row_id for f in findings if f.row_id is not None}
    rows_affected = len(affected)
    clean_pct = None
    if n_rows:
        clean_pct = round(max(0, n_rows - rows_affected) / n_rows * 100, 1)
    return {
        "total": len(findings),
        "error": by.get(Severity.ERROR, 0),
        "warn": by.get(Severity.WARN, 0),
        "info": by.get(Severity.INFO, 0),
        "records": n_rows,
        "rows_affected": rows_affected,
        "clean_pct": clean_pct,
    }


def _aggregate(items: list[Finding]) -> list[dict]:
    """Collapse findings sharing a signature into rows carrying count + sample ids."""
    buckets: dict[tuple, dict] = {}
    for f in items:
        key = (f.field, f.message, f.evidence, f.expected, f.suggested_fix, f.severity)
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "count": 1,
                "sample_ids": [] if f.row_id is None else [f.row_id],
                "field": f.field,
                "message": f.message,
                "evidence": f.evidence,
                "expected": f.expected,
                "suggested_fix": f.suggested_fix,
                "severity": f.severity.value,
                "detail_row": None,  # filled in for shown rows when a DataFrame is given
            }
        else:
            bucket["count"] += 1
            if f.row_id is not None and len(bucket["sample_ids"]) < MAX_SAMPLE_IDS:
                bucket["sample_ids"].append(f.row_id)
    # Largest groups first; sort is stable so ties keep first-seen order.
    return sorted(buckets.values(), key=lambda r: -r["count"])


def _grouped(findings: list[Finding], cap: int, indexed: pd.DataFrame | None) -> list[dict]:
    """Bucket by check, aggregate, cap distinct rows, order most-severe then largest."""
    by_check: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_check[f.check].append(f)

    groups = []
    for check, items in by_check.items():
        sev = min((f.severity for f in items), key=lambda s: _SEV_RANK[s])
        rows = _aggregate(items)
        shown = rows[:cap]
        # Drill-down detail is only needed for the rows we actually render.
        for r in shown:
            first_id = r["sample_ids"][0] if r["sample_ids"] else None
            r["detail_row"] = _row_detail(indexed, first_id)
            r["key"] = _finding_key(check, r)
        title, blurb = describe_check(check)
        sev_by = Counter(f.severity for f in items)
        groups.append(
            {
                "check": check,
                "code": check_code(check),
                "title": title,
                "blurb": blurb,
                "severity": sev.value,
                "sev_label": severity_label(sev.value),
                "n_error": sev_by.get(Severity.ERROR, 0),
                "n_warn": sev_by.get(Severity.WARN, 0),
                "n_info": sev_by.get(Severity.INFO, 0),
                "_rank": _SEV_RANK[sev],
                "count": len(items),
                "distinct": len(rows),
                "rows": shown,
                "hidden_rows": max(0, len(rows) - len(shown)),
                "hidden_findings": sum(r["count"] for r in rows[cap:]),
            }
        )
    groups.sort(key=lambda g: (g["_rank"], -g["count"], g["check"]))
    return groups


def _finding_key(check: str, row: dict) -> str:
    """A stable id for one aggregated finding, for the browser-side triage state.

    Derived from the finding's *content* (check + signature), not its position, so a
    reviewer's keep/dismiss/note decisions survive regenerating the report as long as
    the finding itself is unchanged. Row ids are deliberately excluded: the same issue
    landing on a different sample row is still the same issue to triage."""
    sig = "\x1f".join((check, row["field"] or "", row["message"] or "", row["evidence"] or ""))
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:16]


def _row_detail(indexed: pd.DataFrame | None, row_id) -> list[tuple[str, str]] | None:
    """The full field=value listing for one row, for the drill-down panel."""
    if indexed is None or row_id is None or row_id not in indexed.index:
        return None
    row = indexed.loc[row_id]
    return [(str(c), _fmt(row[c])) for c in indexed.columns]


def _field_summary(findings: list[Finding]) -> list[dict]:
    """Cross-cut: how many findings (by severity) touch each column."""
    by_field: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        by_field[f.field or _NO_FIELD][f.severity] += 1
    rows = [
        {
            "field": field,
            "total": sum(counts.values()),
            "error": counts.get(Severity.ERROR, 0),
            "warn": counts.get(Severity.WARN, 0),
            "info": counts.get(Severity.INFO, 0),
        }
        for field, counts in by_field.items()
    ]
    return sorted(rows, key=lambda r: -r["total"])


def _overview(df: pd.DataFrame, spec: DatasetSpec) -> dict:
    """Context panel: shape, per-column dtype/null-rate, categorical value-counts."""
    data_cols = [c for c in df.columns if c != "row_id"]
    columns = [
        {"name": c, "dtype": str(df[c].dtype), "null_pct": float(df[c].isna().mean() * 100)}
        for c in data_cols
    ]
    categoricals = []
    for c in spec.categorical_columns:
        if c in df.columns:
            vc = df[c].value_counts(dropna=False).head(8)
            categoricals.append(
                {"name": c, "counts": [(str(k), int(v)) for k, v in vc.items()]}
            )
    return {
        "n_rows": len(df),
        "n_cols": len(data_cols),
        "columns": columns,
        "categoricals": categoricals,
    }


def _fmt(value, width: int = 120) -> str:
    if pd.isna(value):
        return "<missing>"
    s = str(value)
    return s if len(s) <= width else s[:width] + "…"


if __name__ == "__main__":
    import argparse
    from datetime import datetime

    from auditor.checks import run_all
    from auditor.datasets import DATASETS, get
    from auditor.load import load

    parser = argparse.ArgumentParser(prog="auditor.report")
    parser.add_argument("--dataset", default=None, choices=sorted(DATASETS))
    parser.add_argument("--out", default="report.html")
    args = parser.parse_args()

    spec = get(args.dataset)
    df = load(spec=spec)
    findings = run_all(df, spec)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    path = write(findings, spec, args.out, df=df, generated_at=stamp)
    print(f"wrote {len(findings):,} findings -> {path}")
