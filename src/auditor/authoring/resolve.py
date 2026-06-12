"""Classify a dry-run, and decide on it -- by model policy or by asking the human.

The unification that makes the autonomy dial cheap: :func:`model_decide` is the whole
brain. "You choose" is a human invoking it on one question; auto-resolution is policy
invoking the same function. So the session's ``--autonomy`` knob needs no extra
machinery -- it only chooses *who* calls :func:`model_decide` and *when* to ask instead.

The model still never asserts a finding: it accepts or skips a *proposed check*; the
deterministic check is what would produce findings if the rule is adopted.
"""

from __future__ import annotations

from dataclasses import dataclass

from auditor.authoring.dryrun import Evidence
from auditor.authoring.proposals import Candidate

# Decision thresholds (slice 1 heuristics; the authoring benchmark hardens these later).
CONF_OK = 0.6          # below this the model defers rather than auto-accept
TINY_RATE = 0.01       # <= this flagged fraction is "barely fires" -> safe to adopt
SUSPICIOUS_RATE = 0.5  # >= this flagged fraction means the bound probably nukes good data

# The three bands a dry-run falls into (drives routing under `balanced` autonomy).
Band = str  # "auto-safe" | "ask" | "suspicious"


@dataclass(frozen=True)
class Resolution:
    """The outcome for one candidate: who decided, what, and why."""

    decided_by: str          # "human" | "model"
    action: str              # "accept" | "edit" | "skip"
    final_params: dict | None
    note: str = ""


def classify(candidate: Candidate, evidence: Evidence) -> Band:
    """Bucket a dry-run by flag-rate and the model's self-confidence.

    ~0% and confident is safe to adopt; ~100% means the bound likely flags good data and
    deserves a human's eye; a plausible fraction in between is the interesting "ask" band.
    """
    if evidence.flag_rate >= SUSPICIOUS_RATE:
        return "suspicious"
    if evidence.flag_rate <= TINY_RATE and candidate.confidence >= CONF_OK:
        return "auto-safe"
    return "ask"


def model_decide(candidate: Candidate, evidence: Evidence) -> Resolution:
    """The auto/"you choose" brain: accept a sound proposal, skip a doubtful one.

    Skips a suspicious dry-run (a bound flagging >= half the rows is probably wrong) and a
    low-confidence proposal (defer to a human), and accepts otherwise -- always recording a
    one-line rationale so an auto decision is auditable, never silent.
    """
    pct = f"{evidence.flag_rate:.2%}"
    if evidence.flag_rate >= SUSPICIOUS_RATE:
        return Resolution("model", "skip", None,
                          f"flags {evidence.flag_count} rows ({pct}); the bound likely "
                          f"rejects valid data, so left for a human.")
    if candidate.confidence < CONF_OK:
        return Resolution("model", "skip", None,
                          f"confidence {candidate.confidence:.2f} below {CONF_OK}; "
                          f"deferring to a human.")
    return Resolution("model", "accept", candidate.params(),
                      f"confident ({candidate.confidence:.2f}); would flag "
                      f"{evidence.flag_count} rows ({pct}), a plausible rate.")


def format_question(candidate: Candidate, evidence: Evidence) -> str:
    """The human-facing question block for one candidate (also used in the auto report)."""
    bound = _describe(candidate)
    head = f"[{candidate.column}] propose: flag {candidate.column} {bound}"
    why = f"  why: {candidate.rationale} (model confidence {candidate.confidence:.2f})"
    if evidence.flag_count:
        eg = f"  e.g. {', '.join(evidence.samples)}" if evidence.samples else ""
        impact = f"  if applied: flags {evidence.flag_count} of {_total(evidence)} rows ({evidence.flag_rate:.2%}).{eg}"
    else:
        impact = "  if applied: flags nothing now (a forward guard)."
    return "\n".join([head, why, impact])


def ask_human(candidate: Candidate, evidence: Evidence) -> Resolution:
    """Show the question and act on the reviewer's choice (interactive).

    Accept adopts the bound; Edit takes new min/max; Skip declines; "You choose" delegates
    to :func:`model_decide` -- the same brain the auto path uses, logged as decided_by=model.
    """
    import typer

    typer.echo(format_question(candidate, evidence))
    choice = typer.prompt("  [a]ccept / [e]dit / [s]kip / [y]ou choose", default="y").strip().lower()[:1]
    if choice == "a":
        return Resolution("human", "accept", candidate.params(), "accepted by reviewer")
    if choice == "e":
        lo = typer.prompt("    min (blank = none)", default="", show_default=False).strip()
        hi = typer.prompt("    max (blank = none)", default="", show_default=False).strip()
        params: dict = {}
        if lo:
            params["min"] = float(lo)
        if hi:
            params["max"] = float(hi)
        # Preserve the reviewer's exclusivity intent from the proposal.
        if candidate.exclusive_min and "min" in params:
            params["exclusive_min"] = True
        if candidate.exclusive_max and "max" in params:
            params["exclusive_max"] = True
        return Resolution("human", "edit", params or None, "edited by reviewer")
    if choice == "s":
        return Resolution("human", "skip", None, "skipped by reviewer")
    return model_decide(candidate, evidence)  # "you choose"


def _describe(candidate: Candidate) -> str:
    parts = []
    if candidate.min is not None:
        parts.append(f"{'<=' if candidate.exclusive_min else '<'} {candidate.min}")
    if candidate.max is not None:
        parts.append(f"{'>=' if candidate.exclusive_max else '>'} {candidate.max}")
    return " or ".join(parts) if parts else "(no bound)"


def _total(evidence: Evidence) -> int:
    return round(evidence.flag_count / evidence.flag_rate) if evidence.flag_rate else evidence.flag_count
