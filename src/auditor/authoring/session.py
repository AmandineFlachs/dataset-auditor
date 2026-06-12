"""Drive one authoring session: propose -> dry-run -> classify -> resolve -> emit.

This is the loop the ``auditor author`` command runs. It honors the ``--autonomy`` dial by
choosing, per candidate, whether to ask the human or let :func:`model_decide` settle it --
the dial is the only thing that changes, because "you choose" and auto-resolution are the
same function (see ``resolve``). The output is a ``range_rules`` spec fragment plus a JSON
decision log, so every adopted rule is traceable to who decided it and the evidence they saw.
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
    """What a session produced: the adopted rules, the emitted fragment, and the log."""

    accepted: dict = field(default_factory=dict)  # column -> range_rules params
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
    """Propose range rules and resolve each one under ``autonomy``.

    ``candidates`` can be injected (for tests / a precomputed proposal); otherwise they are
    proposed from the live model. With no model and no injection there is nothing to do, and
    the session returns an empty result rather than failing.
    """
    if autonomy not in AUTONOMY:
        raise ValueError(f"autonomy must be one of {AUTONOMY}, not {autonomy!r}")
    if candidates is None:
        candidates = propose(df, spec, client=client)

    accepted: dict = {}
    log: list[dict] = []
    for cand in candidates:
        evidence = dry_run(cand, df)
        band = classify(cand, evidence)
        resolution = _resolve(cand, evidence, band, autonomy)
        if resolution.action in ("accept", "edit") and resolution.final_params:
            accepted[cand.column] = resolution.final_params
        log.append({
            "column": cand.column,
            "kind": cand.kind,
            "proposed": cand.params(),
            "rationale": cand.rationale,
            "confidence": cand.confidence,
            "flag_count": evidence.flag_count,
            "flag_rate": round(evidence.flag_rate, 4),
            "samples": evidence.samples,
            "band": band,
            "decided_by": resolution.decided_by,
            "action": resolution.action,
            "final_params": resolution.final_params,
            "note": resolution.note,
        })
    return SessionResult(accepted=accepted, fragment=emit_fragment(accepted, spec.name), log=log)


def _resolve(cand, evidence, band, autonomy):
    """Route one candidate by the autonomy dial (the dial's whole job)."""
    if autonomy == "ask-all":
        return ask_human(cand, evidence)
    if autonomy == "hands-off":
        return model_decide(cand, evidence)
    # balanced: auto-decide the safe band, ask the human about the rest.
    return model_decide(cand, evidence) if band == "auto-safe" else ask_human(cand, evidence)


def emit_fragment(accepted: dict, dataset: str) -> str:
    """Render adopted rules as a ``range_rules=`` snippet pasteable into a DatasetSpec."""
    if not accepted:
        return f"# no range rules adopted for {dataset!r}\nrange_rules={{}}\n"
    lines = [f"# range_rules authored for {dataset!r} (paste into its DatasetSpec)", "range_rules={"]
    for col, params in accepted.items():
        lines.append(f"    {col!r}: {params!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def summarize(result: SessionResult) -> str:
    """A one-line tally for the CLI: adopted vs skipped, and who decided."""
    adopted = len(result.accepted)
    skipped = sum(1 for e in result.log if e["action"] == "skip")
    by_model = sum(1 for e in result.log if e["decided_by"] == "model")
    return (f"{len(result.log)} candidate(s): {adopted} adopted, {skipped} skipped "
            f"({by_model} decided by the model)")
