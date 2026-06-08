"""The shared data contract for the whole tool.

Every check (schema, units, duplicates, pii, labels) returns a list of
``Finding`` objects, and the report layer only ever reads ``Finding`` objects.
Nothing else is shared between checks and the report. That single agreement is
what keeps every part of the codebase independent and individually testable.

If you only ever read one file in this project, read this one.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """How serious a finding is.

    It's an ``Enum`` (not a bare string) so the *set* of valid severities lives
    in exactly one place. You cannot accidentally emit ``"warnn"`` and silently
    break filtering/sorting later — pydantic will reject it at creation time.

    Subclassing ``str`` is a small convenience: a ``Severity`` is still a normal
    string when serialized to JSON / rendered in HTML, so the report layer needs
    no special handling.
    """

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Finding(BaseModel):
    """One thing that might be wrong with one place in the dataset.

    This is the 'common currency' the whole pipeline speaks. A check's entire
    job is to turn messy data into a list of these; the report's entire job is
    to render a list of these. Because the shape is fixed, adding a 6th check or
    swapping HTML for JSON touches no other code.
    """

    check: str
    """Namespaced id of the check that fired, e.g. ``"pii.email"`` or
    ``"units.inconsistent"``. The prefix groups findings in the report."""

    severity: Severity
    """info / warn / error — see :class:`Severity`."""

    row_id: int | None = None
    """*Where* in the dataset. ``None`` means the finding is about the dataset
    as a whole (e.g. 'column X is 40% null') rather than a single row."""

    field: str | None = None
    """*Which* column the finding is about. ``None`` if it spans columns or the
    whole row."""

    message: str
    """Human-readable explanation — this is what a person reads in the report."""

    evidence: str | None = None
    """The actual offending value or snippet, so the finding is verifiable and
    not just an assertion. This is what makes screenshots convincing."""

    expected: str | None = None
    """The value or condition that *should* have held, when a check has a concrete
    one (e.g. 'within [-90, 90]', 'a unique id', 'one of {Fell, Found}'). Paired with
    ``evidence`` it gives the report a Found -> Expected read. ``None`` for checks whose
    finding is a judgement or a 'looks suspicious' signal with no single right answer
    (near-duplicates, PII, model-judged labels), which fall back to the suggested fix."""

    suggested_fix: str | None = None
    """Optional remediation hint, e.g. 'convert K -> °C' or 'drop duplicate'."""


if __name__ == "__main__":
    # Run me directly (`python src/auditor/models.py`) to watch the contract work.
    good = Finding(
        check="pii.email",
        severity=Severity.ERROR,
        row_id=42,
        field="author_note",
        message="Looks like a personal email address in a free-text field.",
        evidence="jane.doe@gmail.com",
        suggested_fix="Redact or hash the address before publishing.",
    )
    print("Valid finding:")
    print(good.model_dump_json(indent=2))

    # Now deliberately break the contract to see pydantic catch it at the source.
    try:
        Finding(check="x", severity="catastrophic", message="bad severity")
    except Exception as exc:  # noqa: BLE001 - demonstration only
        print("\nRejected as expected (severity not in info/warn/error):")
        print(f"  {type(exc).__name__}: {str(exc).splitlines()[0]}")
