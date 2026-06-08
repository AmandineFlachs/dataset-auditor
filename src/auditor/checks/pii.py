"""Personally-identifiable information in free-text columns.

This is the **regex tier**: fast, dependency-free pattern matching for the kinds of
PII that have rigid shapes — emails, phone numbers, US SSNs, credit-card numbers
(Luhn-checked), IPv4 addresses. It is the floor, not the ceiling: the planned
escalation is Presidio NER (names, locations, organizations — things regex can't
catch) and, above that, an LLM pass for context-dependent leaks. Those need a heavy
model / the local server, so they are deferred; this tier runs everywhere, always.

Two deliberate choices:

* **Only configured columns are scanned.** ``DatasetSpec.pii_text_columns`` names the
  free-text fields; numeric science columns are never examined, so a lattice constant
  is never mistaken for a phone number. Both science flagships declare no such
  columns, so PII is demonstrated on a fixture — honestly, since neither dataset
  contains any.
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


def check(df: pd.DataFrame, columns=()) -> list[Finding]:
    """Scan each configured free-text column for PII patterns."""
    findings: list[Finding] = []
    for col in columns:
        if col not in df.columns:
            continue
        for row_id, value in zip(df["row_id"], df[col]):
            if not isinstance(value, str):
                continue
            findings.extend(_scan_cell(int(row_id), col, value))
    return findings


def _scan_cell(row_id: int, col: str, value: str) -> list[Finding]:
    findings: list[Finding] = []
    for det in _DETECTORS:
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
