"""Categorical plausibility, judged by the local LLM.

The deterministic checks answer arithmetic questions (is this out of range? do these
rows share a key?). This one answers a *judgement* question a small local model is
suited to: given everything else in the row and the dataset's domain context, is this
categorical value plausible? It is the first — and only — check that talks to the LLM.

Three principles shape it, all inherited from the rest of the codebase:

* **Generic engine, spec-as-data.** A :class:`~auditor.datasets.LabelRule` names the
  column to judge and the context columns to show the model; no domain knowledge lives
  here. Empty ``label_rules`` means silence.
* **Degrade gracefully.** A local model is a flaky dependency. If the server is
  unreachable — up front or mid-run — the check emits exactly ONE ``info`` finding and
  the deterministic audit is untouched. It can never crash the run.
* **Sample, never scan.** LLM calls cost. The check judges at most ``rule.max_calls``
  *distinct* (value, context) cases per rule, deduplicating identical situations so the
  budget buys breadth. Values outside an optional closed vocabulary are flagged
  deterministically, spending no call at all.

Honesty: both science flagships leave ``label_rules`` empty (their categoricals are
facts, not error-prone labels), so on real data this check is silent by design. It is
proven on a fixture in ``tests/test_labels.py`` — the same posture as ``pii.py``.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field

from auditor.llm import LLMClient, LLMResponseError, LLMUnavailable
from auditor.models import Finding, Severity

# Below this self-rated confidence, a "implausible" verdict is surfaced as INFO, not
# WARN — a small local model's low-confidence negatives should not read as firm alarms.
MIN_CONFIDENCE = 0.6


class LabelVerdict(BaseModel):
    """The model's judgement on one value. Validated, so a bad reply can't flow on."""

    plausible: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


def check(df: pd.DataFrame, rules=(), client: LLMClient | None = None, context: str = "") -> list[Finding]:
    """Judge each rule's categorical column, degrading to one info finding if offline."""
    if not rules:
        return []  # configured off: silence, no skip notice, no calls
    # This check defaults to REASONING mode. On the strict (forced-JSON) path a small
    # reasoning model confabulates and scores at the floor on the leakage-safe benchmark
    # (0.500); letting it think first takes it to 1.000 on held-out data (40/40). See
    # benchmarks/README.md "Results". A caller can inject a strict client to override.
    client = client or LLMClient.from_env(reasoning=True)
    # Decide reachability ONCE, up front (cheap GET /models, never raises).
    if not client.available():
        return [_skipped_finding()]
    findings: list[Finding] = []
    try:
        for rule in rules:
            findings.extend(_apply(df, rule, client, context))
    except LLMUnavailable:
        # Server died mid-run: discard partials so the contract is exactly ONE finding
        # (a skip notice alongside some warnings would be self-contradictory).
        return [_skipped_finding()]
    return findings


def _apply(df: pd.DataFrame, rule, client: LLMClient, context: str) -> list[Finding]:
    if rule.column not in df.columns:
        return []
    ctx_cols = [c for c in rule.context_columns if c in df.columns]
    findings: list[Finding] = []

    # Group candidate rows by (value, *context) so identical situations cost one call;
    # out-of-vocabulary values are certain and flagged without the model.
    groups: dict[tuple, list[int]] = {}
    reps: dict[tuple, pd.Series] = {}
    for _, row in df[df[rule.column].notna()].iterrows():
        value = row[rule.column]
        if rule.allowed and value not in rule.allowed:
            findings.append(_out_of_vocab_finding(int(row["row_id"]), rule, value))
            continue
        key = (str(value),) + tuple(_fmt(row[c]) for c in ctx_cols)
        groups.setdefault(key, []).append(int(row["row_id"]))
        reps.setdefault(key, row)

    # Deterministic head of distinct cases (reproducible for screenshots); the cap
    # bounds spend. LLMUnavailable propagates to check(); LLMResponseError is local.
    for key in list(reps)[: rule.max_calls]:
        try:
            verdict = client.judge(build_label_prompt(rule, reps[key], ctx_cols), LabelVerdict, context=context)
        except LLMResponseError:
            continue  # a malformed reply skips this case — never crash, never fabricate
        if verdict.plausible:
            continue  # the audit reports problems, not confirmations
        severity = Severity.WARN if verdict.confidence >= MIN_CONFIDENCE else Severity.INFO
        check_id = "labels.implausible" if severity is Severity.WARN else "labels.uncertain"
        for row_id in groups[key]:
            findings.append(_verdict_finding(row_id, rule, reps[key], ctx_cols, verdict, check_id, severity))
    return findings


def build_label_prompt(rule, row: pd.Series, ctx_cols: list[str]) -> str:
    """Build the categorical-plausibility prompt for one (value, context) case.

    Kept as a small, separately-testable function so the prompt the check ships can be
    exercised directly. The domain context is injected separately by ``llm.py`` (via the
    ``context=`` arg to ``judge``), so it is not part of this string.
    """
    value = row[rule.column]
    lines = [f"Column {rule.column!r} has value {value!r} for this row."]
    if rule.allowed:
        lines.append(f"Known valid values: {', '.join(rule.allowed)}.")
    if ctx_cols:
        lines.append("Other fields for the same row:")
        lines.extend(f"  {c}={_fmt(row[c])}" for c in ctx_cols)
    lines.append(
        f"Is {value!r} a plausible value for {rule.column!r} given these fields and the "
        "domain context? Answer plausible=false ONLY if it clearly conflicts; treat "
        "borderline or uncertain cases as plausible=true and lower your confidence."
    )
    return "\n".join(lines)


def _context_evidence(row: pd.Series, rule, ctx_cols: list[str]) -> str:
    parts = [f"{rule.column}={_fmt(row[rule.column])}"]
    parts += [f"{c}={_fmt(row[c])}" for c in ctx_cols]
    return " | ".join(parts)


def _verdict_finding(row_id, rule, row, ctx_cols, verdict, check_id, severity) -> Finding:
    return Finding(
        check=check_id,
        severity=severity,
        row_id=row_id,
        field=rule.column,
        message=f"Model judged {rule.column!r} implausible for this row.",
        evidence=f"{_context_evidence(row, rule, ctx_cols)}; model ({verdict.confidence:.2f}): {verdict.reason}",
        suggested_fix="Confirm the category against the listed fields; relabel or correct if it is wrong.",
    )


def _out_of_vocab_finding(row_id: int, rule, value) -> Finding:
    return Finding(
        check="labels.out_of_vocab",
        severity=Severity.WARN,
        row_id=row_id,
        field=rule.column,
        message=f"{rule.column!r} value is outside the known vocabulary.",
        evidence=f"{rule.column}={_fmt(value)} not in {{{', '.join(rule.allowed)}}}",
        expected=f"one of: {', '.join(rule.allowed)}",
        suggested_fix="Correct the value or extend the allowed vocabulary if it is legitimate.",
    )


def _skipped_finding() -> Finding:
    return Finding(
        check="labels.skipped",
        severity=Severity.INFO,
        row_id=None,
        field=None,
        message="labels: LLM checks skipped (server offline)",
        evidence=None,
        suggested_fix=None,
    )


def _fmt(value, width: int = 80) -> str:
    if pd.isna(value):
        return "<missing>"
    s = str(value)
    return s if len(s) <= width else s[:width] + "..."
