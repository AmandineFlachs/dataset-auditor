"""Personally-identifiable information in free-text columns.

This is the **regex tier**: fast, dependency-free pattern matching for the kinds of
PII that have rigid shapes — emails, phone numbers, US SSNs, credit-card numbers
(Luhn-checked), IPv4 addresses. It is the floor, not the ceiling: the planned
escalation is Presidio NER (names, locations, organizations — things regex can't
catch) and, above that, an LLM pass for context-dependent leaks. Those need a heavy
model / the local server, so they are deferred; this tier runs everywhere, always.

Two deliberate choices:

* **Always runs; declaring columns widens the sweep.** If ``DatasetSpec.pii_text_columns``
  names the free-text fields, every detector runs on them. If none are named, the check
  falls back to auto-detecting the text columns and scanning them for the *rigid, low
  false-positive* identifiers only (email, SSN) — so privacy is never an unexamined blind
  spot, while a lattice constant is still never mistaken for a phone number. Declaring
  columns is how you opt into the noisier detectors (phone, card, IPv4).
* **Evidence is masked.** The whole point is to flag a leak; a report that printed the
  raw SSN would *be* the leak. So evidence shows enough to locate the value
  (``j****@e****.com``) without reproducing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from auditor.models import Finding, Severity


@dataclass(frozen=True)
class _Detector:
    kind: str
    severity: Severity
    pattern: re.Pattern
    validate: Callable[[str], bool] | None = None  # optional structural check


def _luhn_ok(text: str) -> bool:
    """Luhn checksum — rejects random 13-16 digit runs that aren't card numbers."""
    digits = [int(c) for c in text if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _ipv4_ok(text: str) -> bool:
    return all(0 <= int(octet) <= 255 for octet in text.split("."))


# Order matters only for readability; every detector runs on every cell.
_DETECTORS: tuple[_Detector, ...] = (
    _Detector("email", Severity.WARN, re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    _Detector(
        "ssn", Severity.ERROR, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    ),
    _Detector(
        "credit_card",
        Severity.ERROR,
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        validate=_luhn_ok,
    ),
    _Detector(
        "phone",
        Severity.WARN,
        re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"),
    ),
    _Detector(
        "ipv4",
        Severity.WARN,
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        validate=_ipv4_ok,
    ),
)

# Detectors safe to run on *auto-detected* columns: rigid shapes that essentially never
# false-positive on scientific data. The noisier detectors (phone/card/ipv4) run only on
# columns a spec explicitly declares as free text.
_RIGID_KINDS = ("email", "ssn")
_RIGID_DETECTORS = tuple(d for d in _DETECTORS if d.kind in _RIGID_KINDS)


def _text_columns(df: pd.DataFrame) -> list[str]:
    """Columns (other than ``row_id``) holding at least one string value."""
    return [
        c for c in df.columns
        if c != "row_id" and df[c].map(lambda v: isinstance(v, str)).any()
    ]


def scannable_columns(df: pd.DataFrame, declared=()) -> list[str]:
    """The columns PII will actually scan: the declared free-text columns when any are
    named, otherwise the auto-detected text columns. Empty only when there is no text."""
    if declared:
        return [c for c in declared if c in df.columns]
    return _text_columns(df)


def check(df: pd.DataFrame, columns=()) -> list[Finding]:
    """Scan for PII. Declared columns get every detector; with none declared, fall back to
    the auto-detected text columns scanned for the rigid identifiers (email, SSN) only."""
    detectors = _DETECTORS if columns else _RIGID_DETECTORS
    findings: list[Finding] = []
    for col in scannable_columns(df, columns):
        for row_id, value in zip(df["row_id"], df[col]):
            if not isinstance(value, str):
                continue
            findings.extend(_scan_cell(int(row_id), col, value, detectors))
    return findings


def _scan_cell(row_id: int, col: str, value: str, detectors=_DETECTORS) -> list[Finding]:
    findings: list[Finding] = []
    for det in detectors:
        for match in det.pattern.findall(value):
            if det.validate and not det.validate(match):
                continue
            # The credit-card pattern can absorb a trailing space/dash; strip it so the
            # masked evidence does not end in a stray separator.
            match = match.strip(" -")
            findings.append(
                Finding(
                    check=f"pii.{det.kind}",
                    severity=det.severity,
                    row_id=row_id,
                    field=col,
                    message=f"Possible {det.kind.replace('_', ' ')} in a free-text field.",
                    evidence=_mask(match),
                    suggested_fix="Redact, hash, or remove the value before publishing.",
                )
            )
    return findings


def _mask(text: str) -> str:
    """Reveal shape, hide content: keep structural separators and first letters,
    star out the rest, so the finding is locatable but not itself a leak."""
    out = []
    for token in re.split(r"([@. -])", text):  # keep the separators
        if token in "@. -" or not token:
            out.append(token)
        elif len(token) <= 1:
            out.append("*")
        else:
            out.append(token[0] + "*" * (len(token) - 1))
    return "".join(out)
