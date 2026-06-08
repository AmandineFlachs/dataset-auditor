"""Tests for the data contract.

Notice these need no dataset, no LLM, no HTML — just the contract. That's the
payoff of keeping `Finding` dependency-free: the spine is trivially testable.
"""

import pytest
from pydantic import ValidationError

from auditor.models import Finding, Severity


def test_minimal_finding():
    """check + severity + message are the only required fields."""
    f = Finding(check="schema.null", severity=Severity.WARN, message="column is empty")
    assert f.row_id is None
    assert f.field is None
    assert f.suggested_fix is None


def test_severity_must_be_valid():
    """A bogus severity is rejected at creation, not silently accepted."""
    with pytest.raises(ValidationError):
        Finding(check="x", severity="catastrophic", message="nope")


def test_severity_serializes_as_plain_string():
    """Because Severity subclasses str, the JSON is report-friendly."""
    f = Finding(check="pii.email", severity=Severity.ERROR, message="m")
    assert '"severity":"error"' in f.model_dump_json().replace(" ", "")
