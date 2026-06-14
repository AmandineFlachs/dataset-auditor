"""Guided rule-authoring: the model proposes checks, a human (or policy) approves them.

Slice 1 is ``range`` only (see ``docs/design/guided-rule-authoring.md``). The flow per
candidate is propose -> dry-run -> classify -> resolve -> emit; the ``--autonomy`` dial
chooses who resolves. The model never asserts a finding -- it proposes a check; the
deterministic check produces findings only once a human or delegated policy adopts it.
"""

from auditor.authoring.dryrun import Evidence, dry_run
from auditor.authoring.proposals import Candidate, propose
from auditor.authoring.resolve import Resolution, classify, model_decide
from auditor.authoring.session import (
    AUTONOMY,
    SessionResult,
    emit_fragment,
    run_session,
    summarize,
)

__all__ = [
    "Candidate", "propose",
    "Evidence", "dry_run",
    "Resolution", "classify", "model_decide",
    "AUTONOMY", "SessionResult", "run_session", "emit_fragment", "summarize",
]
