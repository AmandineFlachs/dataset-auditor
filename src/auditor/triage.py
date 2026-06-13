"""Finding-triage: a deterministic reading order, with the LLM doing only what it can.

A real audit produces many findings (LeMat-Bulk: 363) of unequal importance. Triage
turns that flat list into a prioritized reading order plus a short orientation for a
human reviewer.

Scope is deliberate. The local model is NOT asked to judge whether each issue is a
*genuine defect or an expected artifact* (e.g. the 122 duplicate ids that are really one
material across DFT functionals). That verdict needs domain grounding to get right: a
model that anchors on the generic check message ("this column is expected to be unique")
and an `error` severity will call an expected artifact a defect. Shipping a verdict that
is wrong is worse than not shipping one, so it is withheld. What remains is split by who
is good at what:

* **Deterministic** (no model, never wrong): cluster findings into distinct issue
  types, and order them by severity then affected-row count. This is the priority.
* **LLM, advisory**: a plain-language summary of the audit, and a one-line "what should
  a reviewer check?" per issue -- framed as *verification*, never a fix to apply. The
  model is reliable at orientation and suggesting what to look at; it does not decide
  what is real.

Like the rest of the LLM layer it degrades gracefully (offline -> `None`, a timeout
surfaces as `LLMTimeout`), and it never edits a finding.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from auditor.datasets import DatasetSpec
from auditor.llm import LLMClient, LLMTimeout, LLMUnavailable
from auditor.models import Finding

# Triage reasons over a handful of aggregated issues in one call; the reply is short
# (a summary + one line per issue), but give it headroom over a per-row call.
_TRIAGE_TIMEOUT = 120.0
# Sample evidences shown per issue, enough to characterize it without dumping every row.
_MAX_SAMPLES = 3

# Severity drives the deterministic priority: most serious first, then by volume.
_SEV_RANK = {"error": 0, "warn": 1, "info": 2}
_PRIORITY = {"error": "high", "warn": "medium", "info": "low"}


class IssueNote(BaseModel):
    """The model's advisory note on one issue: what a reviewer should check. No verdict."""

    id: int
    """Index of the issue in the list the model was given, so the note can be matched
    back to the real (deterministically-prioritized) issue group in code."""

    next_check: str
    """One line: what to verify to decide whether this issue matters. A check to run or
    a question to answer for a human, never a deletion/fix to apply blindly."""


class TriageNotes(BaseModel):
    """The LLM's advisory layer: an overall summary plus a per-issue check to run."""

    summary: str
    notes: list[IssueNote] = Field(default_factory=list)


def triage(findings: list[Finding], spec: DatasetSpec, *, client: LLMClient | None = None) -> TriageNotes | None:
    """Get the LLM's advisory summary + per-issue checks, or ``None`` if offline.

    Priority/ordering is computed separately and deterministically (see
    :func:`issue_groups`); this call only adds orientation a human can ignore. Returns
    ``None`` when there is nothing to triage or the server is genuinely absent; a
    timeout propagates as :class:`LLMTimeout` so the caller can report it honestly.
    """
    groups = issue_groups(findings)
    if not groups:
        return None
    client = client or LLMClient.from_env(timeout=_TRIAGE_TIMEOUT)
    if not client.available():
        return None
    try:
        return client.judge(_prompt(groups, spec), TriageNotes, context=spec.domain_context)
    except LLMTimeout:
        raise
    except LLMUnavailable:
        return None


def issue_groups(findings: list[Finding]) -> list[dict]:
    """Collapse findings to distinct issue *types* and order them by priority.

    Coarser than the report's per-row aggregation on purpose: every near-duplicate
    instance, whatever its fingerprint, is one issue here. Each group carries a
    severity-derived ``priority`` and the suggested fix authored by the check itself.
    Ordered deterministically by severity (most serious first) then affected-row count,
    which IS the triage priority -- no model involved, so it is never wrong.
    """
    buckets: dict[tuple, dict] = {}
    for f in findings:
        key = (f.check, f.field, f.message)
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "check": f.check,
                "field": f.field,
                "message": f.message,
                "severity": f.severity.value,
                "priority": _PRIORITY.get(f.severity.value, "low"),
                "suggested_fix": f.suggested_fix,
                "count": 1,
                "samples": [f.evidence] if f.evidence else [],
            }
        else:
            bucket["count"] += 1
            if f.evidence and len(bucket["samples"]) < _MAX_SAMPLES and f.evidence not in bucket["samples"]:
                bucket["samples"].append(f.evidence)
    return sorted(
        buckets.values(),
        key=lambda b: (_SEV_RANK.get(b["severity"], 3), -b["count"]),
    )


def _prompt(groups: list[dict], spec: DatasetSpec) -> str:
    lines = [
        "Below are the distinct data-quality issues an automated audit raised on this "
        "dataset, already ordered by priority (severity, then how many rows each "
        "affects). Your job is ORIENTATION for a human reviewer, in two parts:",
        "  1. a short, neutral summary (1-2 sentences) of what the audit found and "
        "where the volume is. Do NOT declare whether issues are real defects.",
        "  2. for each issue, one line on what the reviewer should CHECK or VERIFY to "
        "decide whether it matters -- a question to answer or a check to run, using the "
        "domain context. Never recommend deleting or 'cleaning' data outright; the same "
        "pattern can be intentional (the domain context may explain it).",
        "",
        f"Dataset: {spec.name}",
        "",
        "Issues (in priority order):",
    ]
    for i, g in enumerate(groups):
        field = g["field"] or "(whole dataset)"
        lines.append(
            f"[{i}] priority={g['priority']} check={g['check']} field={field} "
            f"affected_rows={g['count']}"
        )
        lines.append(f"    message: {g['message']}")
        for s in g["samples"]:
            lines.append(f"    e.g. {s}")
    lines.append("")
    lines.append("Return a 'summary' and a 'notes' list with one entry per issue above (use its [id]).")
    return "\n".join(lines)


def to_markdown(notes: TriageNotes | None, spec: DatasetSpec, groups: list[dict]) -> str:
    """Render the triage: deterministic priority order, with the LLM's check per issue.

    ``groups`` (from :func:`issue_groups`) is the source of truth for priority, counts
    and the check-authored fix; ``notes`` (which may be ``None`` if the LLM was offline)
    only adds the advisory 'what to check' line, so the triage is useful with or without
    a model.
    """
    by_id = {n.id: n for n in (notes.notes if notes else [])}
    out = [f"# Triage: {spec.name}", ""]
    if notes and notes.summary:
        out += [notes.summary, ""]
    out += ["## Issues, highest priority first", ""]
    for i, g in enumerate(groups):
        field = g["field"] or "whole dataset"
        out.append(f"### [{g['priority'].upper()}] {g['check']} - {field} ({g['count']} rows)")
        out.append(f"- {g['message']}")
        if g.get("suggested_fix"):
            out.append(f"- **Suggested fix:** {g['suggested_fix']}")
        note = by_id.get(i)
        if note:
            out.append(f"- **What to check:** {note.next_check}")
        out.append("")
    framing = (
        "*Priority is deterministic (severity, then affected rows). The summary and "
        "'what to check' lines are an advisory orientation from a local model -- it "
        "suggests what to verify, it does not decide what is a real defect.*"
    )
    out.append("---\n" + framing)
    return "\n".join(out)
