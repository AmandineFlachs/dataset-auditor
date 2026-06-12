"""Drive one authoring session: propose -> dry-run -> classify -> resolve -> emit.

This is the loop ``auditor author`` runs. It honors the ``--autonomy`` dial by choosing, per
candidate, whether to ask the human or let :func:`model_decide` settle it -- the dial is the
only thing that changes, because "you choose" and auto-resolution are the same function (see
``resolve``). The output is a ``DatasetSpec`` fragment (one section per rule kind adopted)
plus a JSON decision log, so every adopted rule is traceable to who decided it and the
evidence they saw.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from auditor.authoring.dryrun import dry_run
from auditor.authoring.proposals import Candidate, propose
from auditor.authoring.resolve import ask_human, classify, model_decide

AUTONOMY = ("ask-all", "balanced", "hands-off")


@dataclass
class SessionResult:
    """What a session produced: the adopted candidates, the emitted fragment, and the log."""

    accepted: list[Candidate] = field(default_factory=list)
    fragment: str = ""
    log: list[dict] = field(default_factory=list)


def run_session(
    df: pd.DataFrame,
    spec,
    autonomy: str = "balanced",
    *,
    client=None,
    candidates: list[Candidate] | None = None,
) -> SessionResult:
    """Propose rules and resolve each under ``autonomy``.

    ``candidates`` can be injected (for tests / a precomputed proposal); otherwise they are
    proposed from the live model. With no model and no injection there is nothing to do, and
    the session returns an empty result rather than failing.
    """
    if autonomy not in AUTONOMY:
        raise ValueError(f"autonomy must be one of {AUTONOMY}, not {autonomy!r}")
    if candidates is None:
        candidates = propose(df, spec, client=client)

    accepted: list[Candidate] = []
    log: list[dict] = []
    for cand in candidates:
        evidence = dry_run(cand, df)
        band = classify(cand, evidence)
        resolution = _resolve(cand, evidence, band, autonomy, df)
        if resolution.final is not None:
            accepted.append(resolution.final)
        log.append({
            "kind": cand.kind,
            "rule": cand.describe(),
            "rationale": cand.rationale,
            "confidence": cand.confidence,
            "flag_count": evidence.flag_count,
            "flag_rate": round(evidence.flag_rate, 4),
            "samples": evidence.samples,
            "band": band,
            "decided_by": resolution.decided_by,
            "action": resolution.action,
            "note": resolution.note,
        })
    return SessionResult(accepted=accepted, fragment=emit_fragment(accepted, spec.name), log=log)


def _resolve(cand, evidence, band, autonomy, df):
    """Route one candidate by the autonomy dial (the dial's whole job)."""
    if autonomy == "ask-all":
        return ask_human(cand, evidence, df)
    if autonomy == "hands-off":
        return model_decide(cand, evidence)
    # balanced: auto-decide the safe band, ask the human about the rest.
    return model_decide(cand, evidence) if band == "auto-safe" else ask_human(cand, evidence, df)


def emit_fragment(accepted: list[Candidate], dataset: str) -> str:
    """Render adopted candidates as DatasetSpec fields, one section per rule kind.

    The output is valid Python (with the needed rule-class imports) that pastes into a spec.
    """
    by_kind: dict[str, list[Candidate]] = {}
    for c in accepted:
        by_kind.setdefault(c.kind, []).append(c)
    if not accepted:
        return f"# no rules adopted for {dataset!r}\n"

    imports = [n for k, n in (("consistency", "ConsistencyRule"),
                              ("near_dup", "NearDupRule"),
                              ("formula", "FormulaRule")) if k in by_kind]
    lines = [f"# DatasetSpec fields authored for {dataset!r} (paste into its spec)"]
    if imports:
        lines.append(f"from auditor.datasets import {', '.join(sorted(imports))}")
    lines.append("")

    if "range" in by_kind:
        lines.append("range_rules={")
        for c in by_kind["range"]:
            lines.append(f"    {c.column!r}: {c.range_params()!r},")
        lines.append("}")
    if "key" in by_kind:
        keys = by_kind["key"]
        lines.append(f"key_column={keys[0].column!r}")
        if len(keys) > 1:
            others = ", ".join(repr(k.column) for k in keys[1:])
            lines.append(f"# note: also proposed as key but key_column is singular: {others}")
    for kind, fieldname in (("consistency", "consistency_rules"),
                            ("near_dup", "near_dup_rules"),
                            ("formula", "formula_rules")):
        if kind in by_kind:
            lines.append(f"{fieldname}=(")
            for c in by_kind[kind]:
                lines.append(f"    {c.to_rule()!r},")
            lines.append(")")
    return "\n".join(lines) + "\n"


def summarize(result: SessionResult) -> str:
    """A one-line tally for the CLI: adopted vs skipped, and who decided."""
    adopted = len(result.accepted)
    skipped = sum(1 for e in result.log if e["action"] == "skip")
    by_model = sum(1 for e in result.log if e["decided_by"] == "model")
    return (f"{len(result.log)} candidate(s): {adopted} adopted, {skipped} skipped "
            f"({by_model} decided by the model)")
