"""Turn a reviewer's report decisions into labelled benchmark cases.

The HTML report lets a human keep/dismiss/flag each issue; this module converts those
decisions into the SAME verdict-case shape the benchmark grades, so every audit becomes
test data for "which local model can judge this domain?" (see :mod:`auditor.modelselect`).

The mapping that closes the loop:

    keep    -> real_defect        (the human confirmed it is a genuine problem)
    dismiss -> expected_artifact  (the human judged it expected/benign)
    review / undecided -> dropped (no ground-truth label yet)

A subtlety the design turns to its advantage: the report aggregates *per evidence*
(check+field+message+evidence), but a verdict case is *per issue type*
(check+field+message) -- the coarser unit :func:`auditor.triage.issue_groups` already
produces. So :func:`to_cases` takes the canonical issue groups (re-derived from a fresh
audit, the single source for ``samples``/``count``) and uses the export ONLY to attach the
human's label, aggregating the per-evidence decisions for an issue into one verdict. The
model never originates the label; the human does, and the deterministic groups supply the
shape.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from auditor.modelselect import load_cases  # the shared jsonl reader (no harness dep)

# How a report status maps to a verdict label. "review"/missing carry no label.
_STATUS_VERDICT = {"keep": "real_defect", "dismiss": "expected_artifact"}


def load_export(path: str | Path) -> list[dict]:
    """Read a ``decisions-*.json`` export (a JSON array of decided issues)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("decisions export must be a JSON array of issue decisions")
    return data


def issue_id(check: str, field: str | None, message: str) -> str:
    """A stable, readable id for an issue type (check+field+message).

    Readable prefix for humans scanning the cases file, plus a short content hash so two
    issues that share check+field but differ in message don't collide.
    """
    sig = "\x1f".join((check, field or "", message))
    digest = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]
    return f"{check}-{field or 'dataset'}-{digest}".replace(" ", "_")


def verdict_for(statuses: list[str]) -> str | None:
    """Aggregate an issue's per-evidence decisions into one verdict, or ``None``.

    keep -> real_defect, dismiss -> expected_artifact. A mix of keeps and dismisses for
    the same issue type is a genuine conflict (the human disagreed with themselves across
    instances) and yields ``None`` -- flagged, not silently resolved. Only ``review`` or
    no decision also yields ``None``.
    """
    keeps = sum(1 for s in statuses if s == "keep")
    dismisses = sum(1 for s in statuses if s == "dismiss")
    if keeps and dismisses:
        return None
    if keeps:
        return "real_defect"
    if dismisses:
        return "expected_artifact"
    return None


def _decisions_by_issue(export: list[dict]) -> dict[tuple, tuple[str | None, str]]:
    """Group export rows by (check, field, message) -> (verdict, first note)."""
    grouped: dict[tuple, list[dict]] = {}
    for d in export:
        key = (d["check"], d.get("field") or "", d["message"])
        grouped.setdefault(key, []).append(d)
    out: dict[tuple, tuple[str | None, str]] = {}
    for key, rows in grouped.items():
        verdict = verdict_for([r.get("status") for r in rows])
        note = next((r.get("note") for r in rows if r.get("note")), "")
        out[key] = (verdict, note)
    return out


def to_cases(groups: list[dict], export: list[dict]) -> tuple[list[dict], dict]:
    """Build verdict cases from canonical issue ``groups`` + the human ``export``.

    ``groups`` is :func:`auditor.triage.issue_groups` output (the case shape's source of
    truth). Returns ``(cases, summary)`` where summary counts labelled / conflicted /
    undecided issues, so the caller can report honestly what was and wasn't captured.
    """
    decisions = _decisions_by_issue(export)
    cases: list[dict] = []
    conflict = undecided = 0
    for g in groups:
        key = (g["check"], g.get("field") or "", g["message"])
        info = decisions.get(key)
        if info is None:
            undecided += 1
            continue
        verdict, note = info
        if verdict is None:
            conflict += 1
            continue
        cases.append({
            "id": issue_id(g["check"], g.get("field"), g["message"]),
            "check": g["check"],
            "field": g.get("field"),
            "severity": g["severity"],
            "count": g["count"],
            "message": g["message"],
            "samples": g.get("samples", []),
            "expected": verdict,
            "note": note,
        })
    return cases, {"labeled": len(cases), "conflict": conflict, "undecided": undecided}


def write_cases(cases: list[dict], out_path: str | Path, *, append: bool = True) -> int:
    """Write cases to a JSONL file (harness-compatible); merge by id when appending.

    Returns the total number of cases in the file afterwards. New cases with an existing
    id overwrite (a re-captured decision is the fresher truth).
    """
    out_path = Path(out_path)
    by_id: dict[str, dict] = {}
    if append and out_path.exists():
        for c in load_cases(out_path):
            by_id[c["id"]] = c
    for c in cases:
        by_id[c["id"]] = c
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(c, ensure_ascii=False) for c in by_id.values()]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(by_id)
