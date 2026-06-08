"""Offline tests for finding-triage (mocked client).

Triage is split: priority/ordering is deterministic (no model), and the LLM only adds
an advisory summary + a 'what to check' line per issue. The tests pin both: the
deterministic part works with no server at all, and the advisory part degrades
gracefully.
"""

import httpx
import pytest

from auditor import triage
from auditor.datasets import LEMAT_BULK
from auditor.llm import LLMClient, LLMTimeout
from auditor.models import Finding, Severity


def _findings():
    # Three issue *types*: a 1-row error (duplicate key), a 3-row warn (near-dup), and a
    # 1-row warn (null rate). The duplicate of the near-dup signature proves aggregation
    # collapses by (check, field, message).
    return [
        Finding(check="duplicates.duplicate_key", severity=Severity.ERROR, row_id=9, field="immutable_id",
                message="dup key", evidence="immutable_id=agm-1", suggested_fix="check it"),
        Finding(check="near_dup.shared_content", severity=Severity.WARN, row_id=1, field="entalpic_fingerprint",
                message="same content", evidence="fp=aaa shared by {mp-1, oqmd-2}"),
        Finding(check="near_dup.shared_content", severity=Severity.WARN, row_id=2, field="entalpic_fingerprint",
                message="same content", evidence="fp=bbb shared by {mp-3, oqmd-4}"),
        Finding(check="near_dup.shared_content", severity=Severity.WARN, row_id=3, field="entalpic_fingerprint",
                message="same content", evidence="fp=ccc shared by {mp-5, oqmd-6}"),
        Finding(check="schema.high_null_rate", severity=Severity.WARN, row_id=None, field="dos_ef",
                message="37% null", evidence="dos_ef null 0.37"),
    ]


_NOTES_JSON = (
    '{"summary":"An error-level duplicate key plus some warnings.",'
    '"notes":[{"id":0,"next_check":"are the duplicate ids the same material across functionals?"},'
    '{"id":1,"next_check":"are the shared fingerprints cross-source ingests?"},'
    '{"id":2,"next_check":"is dos_ef only computed for metals?"}]}'
)


def _completion(content):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def _client_for(chat, *, models_exc=False):
    def handler(req):
        if req.url.path.endswith("/models"):
            if models_exc:
                raise httpx.ConnectError("down", request=req)
            return httpx.Response(200, json={"data": []})
        return chat(req) if callable(chat) else _completion(chat)

    return LLMClient(transport=httpx.MockTransport(handler))


# -- deterministic aggregation + priority (no model) --------------------------


def test_issue_groups_collapse_and_order_by_severity_then_count():
    groups = triage.issue_groups(_findings())
    assert len(groups) == 3
    # error first (priority high), then the larger warn, then the smaller warn.
    assert [g["check"] for g in groups] == [
        "duplicates.duplicate_key", "near_dup.shared_content", "schema.high_null_rate"
    ]
    assert groups[0]["priority"] == "high" and groups[0]["severity"] == "error"
    assert groups[1]["priority"] == "medium" and groups[1]["count"] == 3
    assert len(groups[1]["samples"]) <= triage._MAX_SAMPLES


def test_issue_groups_empty_for_no_findings():
    assert triage.issue_groups([]) == []


# -- the LLM advisory layer ---------------------------------------------------


def test_triage_returns_summary_and_notes():
    notes = triage.triage(_findings(), LEMAT_BULK, client=_client_for(_NOTES_JSON))
    assert notes is not None
    assert notes.summary
    assert {n.id for n in notes.notes} == {0, 1, 2}
    assert "across functionals" in notes.notes[0].next_check


def test_triage_none_when_no_findings():
    # No findings -> nothing to triage, and the server is never contacted.
    assert triage.triage([], LEMAT_BULK, client=_client_for(_NOTES_JSON)) is None


def test_triage_none_when_offline():
    assert triage.triage(_findings(), LEMAT_BULK, client=_client_for(_NOTES_JSON, models_exc=True)) is None


def test_triage_surfaces_timeout():
    def chat(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(LLMTimeout):
        triage.triage(_findings(), LEMAT_BULK, client=_client_for(chat))


def test_prompt_is_aggregated_orientation_not_a_verdict():
    captured = {}

    def chat(req):
        captured["body"] = req.content.decode()
        return _completion(_NOTES_JSON)

    triage.triage(_findings(), LEMAT_BULK, client=_client_for(chat))
    body = captured["body"].lower()
    assert "affected_rows=3" in body            # aggregate count, not three separate rows
    assert "check or verify" in body            # orientation framing
    assert "do not declare whether issues are real defects" in body  # the verdict is NOT asked for


# -- markdown: deterministic with or without the LLM --------------------------


def test_to_markdown_combines_priority_and_notes():
    findings = _findings()
    groups = triage.issue_groups(findings)
    notes = triage.triage(findings, LEMAT_BULK, client=_client_for(_NOTES_JSON))
    md = triage.to_markdown(notes, LEMAT_BULK, groups)
    assert "# Triage: lemat_bulk" in md
    assert "[HIGH] duplicates.duplicate_key" in md   # deterministic priority label
    assert "3 rows" in md                            # count from the matched group
    assert "What to check" in md                     # the advisory line is rendered
    assert "across functionals" in md


def test_to_markdown_works_without_llm_notes():
    # The priority order must render even when the model was offline (notes=None).
    groups = triage.issue_groups(_findings())
    md = triage.to_markdown(None, LEMAT_BULK, groups)
    assert "[HIGH] duplicates.duplicate_key" in md
    assert "What to check" not in md  # no advisory line without the model
