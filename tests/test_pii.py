"""Crafted-row tests for the PII regex check.

Neither science flagship has free-text columns, so PII is exercised entirely on
planted fixtures. These also pin the two design choices: Luhn validation (no false
positives on random digit runs) and masked evidence (the finding must not reproduce
the value it flags).
"""

import pandas as pd

from auditor.checks import pii


def _scan(value, col="note"):
    df = pd.DataFrame({"row_id": [0], col: [value]})
    return pii.check(df, columns=[col])


def test_email_detected_and_masked():
    findings = _scan("contact jane.doe@example.com please")
    assert len(findings) == 1
    f = findings[0]
    assert f.check == "pii.email"
    assert f.severity.value == "warn"
    # The raw value must not appear; the mask keeps shape only.
    assert "jane.doe@example.com" not in f.evidence
    assert "@" in f.evidence and f.evidence.startswith("j")


def test_ssn_is_an_error():
    findings = _scan("ssn 123-45-6789")
    assert [f.check for f in findings] == ["pii.ssn"]
    assert findings[0].severity.value == "error"
    assert "123-45-6789" not in findings[0].evidence


def test_mask_reveals_only_first_char_of_each_token():
    # Pins the "reveal shape, hide content" promise, not just "raw value absent":
    # every separator-delimited token keeps its first char and stars the rest.
    findings = _scan("ssn 123-45-6789")
    assert findings[0].evidence == "1**-4*-6***"


def test_valid_credit_card_detected():
    # 4111 1111 1111 1111 is the canonical Luhn-valid Visa test number.
    findings = _scan("card 4111 1111 1111 1111")
    kinds = {f.check for f in findings}
    assert "pii.credit_card" in kinds


def test_luhn_rejects_random_digit_run():
    # Same length, not Luhn-valid -> not flagged as a card.
    findings = _scan("ref 1234 5678 9012 3456")
    assert all(f.check != "pii.credit_card" for f in findings)


def test_ipv4_detected_but_invalid_octets_rejected():
    assert any(f.check == "pii.ipv4" for f in _scan("host 192.168.0.1"))
    assert all(f.check != "pii.ipv4" for f in _scan("version 999.999.999.999"))


def test_clean_text_yields_nothing():
    assert _scan("a perfectly ordinary sentence about meteorites") == []


def test_non_string_and_missing_columns_are_safe():
    df = pd.DataFrame({"row_id": [0, 1], "mass_g": [10.0, 20.0]})
    # Numeric column not listed -> never scanned; listed-but-absent column -> skipped.
    assert pii.check(df, columns=["mass_g"]) == []
    assert pii.check(df, columns=["absent"]) == []


def test_multiple_columns_scanned():
    df = pd.DataFrame(
        {"row_id": [0], "a": ["x@y.com"], "b": ["call 415-555-2671"]}
    )
    kinds = {f.check for f in pii.check(df, columns=["a", "b"])}
    assert "pii.email" in kinds
    assert "pii.phone" in kinds
