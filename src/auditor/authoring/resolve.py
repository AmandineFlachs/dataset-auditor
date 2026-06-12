"""Classify a dry-run, and decide on it -- by model policy or by asking the human.

The unification that makes the autonomy dial cheap: :func:`model_decide` is the whole brain.
"You choose" is a human invoking it on one question; auto-resolution is policy invoking the
same function. So the session's ``--autonomy`` knob needs no extra machinery -- it only
chooses *who* calls :func:`model_decide` and *when* to ask instead.

The model still never asserts a finding: it accepts or skips a *proposed check*; the
deterministic check is what would produce findings if the rule is adopted. A :class:`Resolution`
carries the ``final`` candidate to emit (possibly edited), or ``None`` when skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from auditor.authoring.dryrun import Evidence, dry_run
from auditor.authoring.proposals import Candidate

# Decision thresholds (slice heuristics; the authoring benchmark hardens these later).
CONF_OK = 0.6          # below this the model defers rather than auto-accept
TINY_RATE = 0.01       # <= this flagged fraction is "barely fires" -> safe to adopt
SUSPICIOUS_RATE = 0.5  # >= this flagged fraction means the rule probably flags good data

Band = str  # "auto-safe" | "ask" | "suspicious"


@dataclass(frozen=True)
class Resolution:
    """The outcome for one candidate: who decided, what, the rule to emit, and why."""

    decided_by: str            # "human" | "model"
    action: str                # "accept" | "edit" | "skip"
    final: Candidate | None    # the candidate to adopt (possibly edited); None if skipped
    note: str = ""


def classify(candidate: Candidate, evidence: Evidence) -> Band:
    """Bucket a dry-run by flag-rate and the model's self-confidence.

    ~0% and confident is safe to adopt; ~most rows means the rule likely flags good data and
    deserves a human's eye; a plausible fraction in between is the interesting "ask" band.
    """
    if evidence.flag_rate >= SUSPICIOUS_RATE:
        return "suspicious"
    if evidence.flag_rate <= TINY_RATE and candidate.confidence >= CONF_OK:
        return "auto-safe"
    return "ask"


def model_decide(candidate: Candidate, evidence: Evidence) -> Resolution:
    """The auto/"you choose" brain: accept a sound proposal, skip a doubtful one.

    Skips a suspicious dry-run (a rule flagging >= half the rows probably rejects valid data)
    and a low-confidence proposal (defer to a human), accepting otherwise -- always with a
    one-line rationale so an auto decision is auditable, never silent.
    """
    pct = f"{evidence.flag_rate:.2%}"
    if evidence.flag_rate >= SUSPICIOUS_RATE:
        return Resolution("model", "skip", None,
                          f"flags {evidence.flag_count} rows ({pct}); the rule likely rejects "
                          f"valid data, so left for a human.")
    if candidate.confidence < CONF_OK:
        return Resolution("model", "skip", None,
                          f"confidence {candidate.confidence:.2f} below {CONF_OK}; deferring "
                          f"to a human.")
    return Resolution("model", "accept", candidate,
                      f"confident ({candidate.confidence:.2f}); would flag "
                      f"{evidence.flag_count} rows ({pct}), a plausible rate.")


def impact(evidence: Evidence) -> str:
    """One-line 'if applied' impact for a dry-run (shared by the question and edit feedback)."""
    if not evidence.flag_count:
        return "flags nothing now (a forward guard)."
    eg = f"  e.g. {', '.join(evidence.samples)}" if evidence.samples else ""
    return f"flags {evidence.flag_count} of {_total(evidence)} rows ({evidence.flag_rate:.2%}).{eg}"


def format_question(candidate: Candidate, evidence: Evidence) -> str:
    """The human-facing question block for one candidate (also used in the auto report)."""
    head = f"[{candidate.kind}] propose: {candidate.describe()}"
    why = f"  why: {candidate.rationale} (model confidence {candidate.confidence:.2f})"
    return "\n".join([head, why, f"  if applied: {impact(evidence)}"])


def ask_human(candidate: Candidate, evidence: Evidence, df) -> Resolution:
    """Show the question and act on the reviewer's choice (interactive).

    Accept adopts the rule; Edit (range only) takes new min/max, RE-DRY-RUNS the edited
    bounds and shows their real impact before the reviewer confirms (so a fumbled edit is
    caught, not shipped silently); Skip declines; "You choose" delegates to
    :func:`model_decide` -- the same brain the auto path uses, logged as model.
    """
    import typer

    typer.echo(format_question(candidate, evidence))
    options = "[a]ccept / [e]dit / [s]kip / [y]ou choose" if candidate.kind == "range" else \
              "[a]ccept / [s]kip / [y]ou choose"
    choice = typer.prompt(f"  {options}", default="y").strip().lower()[:1]
    if choice == "a":
        return Resolution("human", "accept", candidate, "accepted by reviewer")
    if choice == "e" and candidate.kind == "range":
        return _edit(candidate, df, typer)
    if choice == "s":
        return Resolution("human", "skip", None, "skipped by reviewer")
    return model_decide(candidate, evidence)  # "you choose"


def _edit(candidate: Candidate, df, typer) -> Resolution:
    """Take new bounds, re-dry-run them, show the impact, and confirm before adopting."""
    lo = typer.prompt("    min (blank = none)", default="", show_default=False).strip()
    hi = typer.prompt("    max (blank = none)", default="", show_default=False).strip()
    edited = candidate.model_copy(update={
        "min": float(lo) if lo else None,
        "max": float(hi) if hi else None,
    })
    if not edited.range_params():
        return Resolution("human", "skip", None, "edited to no bound -> skipped")
    new_ev = dry_run(edited, df)
    typer.echo(f"    edited -> {impact(new_ev)}")
    if typer.confirm("    adopt this edited rule?", default=True):
        return Resolution("human", "edit", edited, f"edited by reviewer; now flags {new_ev.flag_count} rows")
    return Resolution("human", "skip", None, "edited rule rejected after re-dry-run")


def _total(evidence: Evidence) -> int:
    return round(evidence.flag_count / evidence.flag_rate) if evidence.flag_rate else evidence.flag_count
