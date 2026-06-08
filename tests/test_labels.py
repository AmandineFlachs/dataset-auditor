"""Offline tests for the LLM-judged categorical-plausibility check.

No server is contacted: every test injects an ``httpx.MockTransport`` whose handler
routes ``GET /models`` (for available()) and ``POST /chat/completions`` (for judge)
to canned responses. This is what lets an LLM-backed check be tested in CI without
vLLM running. The flagships declare no label_rules, so this engine is proven here.
"""

import httpx
import pandas as pd

from auditor.checks import labels
from auditor.datasets import LEMAT_BULK, METEORITES, LabelRule
from auditor.llm import LLMClient


def _verdict(plausible: bool, confidence: float, reason: str = "r") -> str:
    return f'{{"plausible": {str(plausible).lower()}, "confidence": {confidence}, "reason": "{reason}"}}'


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def _client_for(chat, *, models_exc: bool = False, **kwargs) -> LLMClient:
    """Client whose /models is OK (unless models_exc) and whose /chat is `chat`
    (a callable handler, or a string returned as the completion content)."""
    def handler(req):
        if req.url.path.endswith("/models"):
            if models_exc:
                raise httpx.ConnectError("down", request=req)
            return httpx.Response(200, json={"data": []})
        return chat(req) if callable(chat) else _completion(chat)

    return LLMClient(transport=httpx.MockTransport(handler), **kwargs)


def _df():
    # rows 0 and 2 share (category=A, mass_g=10.0) -> one dedup group.
    return pd.DataFrame({"row_id": [0, 1, 2], "category": ["A", "B", "A"], "mass_g": [10.0, 20.0, 10.0]})


RULE = LabelRule(column="category", context_columns=("mass_g",))


# -- configured off / degradation (the core requirement) ----------------------


def test_no_rules_is_silent():
    client = _client_for(_verdict(False, 0.9))
    assert labels.check(_df(), rules=(), client=client) == []
    assert client.calls_made == 0


def test_unavailable_server_emits_single_skip():
    client = _client_for(_verdict(False, 0.9), models_exc=True)
    findings = labels.check(_df(), rules=[RULE], client=client)
    assert len(findings) == 1
    f = findings[0]
    assert f.check == "labels.skipped" and f.severity.value == "info" and f.row_id is None
    assert f.message == "labels: LLM checks skipped (server offline)"
    assert client.calls_made == 0  # judge never attempted


def test_midrun_unavailable_emits_exactly_one_skip():
    def chat(req):
        raise httpx.ConnectError("died", request=req)

    # available() passes, but the first judge call dies -> exactly one skip, no partials.
    client = _client_for(chat)
    findings = labels.check(_df(), rules=[RULE], client=client)
    assert [f.check for f in findings] == ["labels.skipped"]


# -- happy path ---------------------------------------------------------------


def test_flags_implausible_as_warn():
    client = _client_for(_verdict(False, 0.9, "A is too light"))
    findings = [f for f in labels.check(_df(), rules=[RULE], client=client) if f.check == "labels.implausible"]
    assert findings and all(f.severity.value == "warn" and f.field == "category" for f in findings)
    assert any("A is too light" in f.evidence for f in findings)


def test_plausible_produces_no_findings():
    client = _client_for(_verdict(True, 0.95))
    assert labels.check(_df(), rules=[RULE], client=client) == []


def test_low_confidence_negative_is_info_not_warn():
    client = _client_for(_verdict(False, 0.3))
    findings = labels.check(_df(), rules=[RULE], client=client)
    assert findings and all(f.check == "labels.uncertain" and f.severity.value == "info" for f in findings)


# -- sampling / dedup ---------------------------------------------------------


def test_respects_max_calls():
    df = pd.DataFrame({"row_id": list(range(6)), "category": list("ABCDEF"), "mass_g": [1.0, 2, 3, 4, 5, 6]})
    rule = LabelRule(column="category", context_columns=("mass_g",), max_calls=2)
    client = _client_for(_verdict(False, 0.9))
    labels.check(df, rules=[rule], client=client)
    assert client.calls_made == 2  # only the cap's worth of distinct cases judged


def test_dedup_judges_shared_case_once_and_fans_out():
    client = _client_for(_verdict(False, 0.9))
    findings = labels.check(_df(), rules=[RULE], client=client)
    # (A,10) judged once + (B,20) once = 2 calls, fewer than the 3 rows.
    assert client.calls_made == 2
    a_rows = {f.row_id for f in findings if f.check == "labels.implausible"}
    assert {0, 2}.issubset(a_rows)  # both A rows flagged from the single verdict


# -- edge / robustness --------------------------------------------------------


def test_response_error_skips_case_and_continues():
    def chat(req):
        body = req.content.decode()
        return _completion("not json at all") if "BAD" in body else _completion(_verdict(False, 0.9))

    df = pd.DataFrame({"row_id": [0, 1], "category": ["BAD", "GOOD"], "mass_g": [1.0, 2.0]})
    rule = LabelRule(column="category", context_columns=("mass_g",))
    findings = labels.check(df, rules=[rule], client=_client_for(chat))
    # BAD's malformed reply is skipped (no crash, no finding); only GOOD survives.
    assert {f.row_id for f in findings} == {1}


def test_out_of_vocab_flagged_without_llm_call():
    df = pd.DataFrame({"row_id": [0, 1], "category": ["pbe", "zzz"], "mass_g": [1.0, 2.0]})
    rule = LabelRule(column="category", context_columns=("mass_g",), allowed=("pbe", "scan"))
    client = _client_for(_verdict(True, 0.9))  # 'pbe' judged plausible -> no finding
    findings = labels.check(df, rules=[rule], client=client)
    oov = [f for f in findings if f.check == "labels.out_of_vocab"]
    assert len(oov) == 1 and oov[0].row_id == 1
    assert client.calls_made == 1  # only the in-vocab value spent a call


def test_missing_column_returns_empty():
    client = _client_for(_verdict(False, 0.9))
    assert labels.check(_df(), rules=[LabelRule(column="absent")], client=client) == []
    assert client.calls_made == 0


def test_prompt_includes_value_context_and_domain_context():
    captured = {}

    def chat(req):
        captured["body"] = req.content.decode()
        return _completion(_verdict(True, 0.9))

    labels.check(_df(), rules=[RULE], client=_client_for(chat), context="mass_g is grams and must be > 0")
    body = captured["body"]
    assert "category" in body and "mass_g" in body
    assert "mass_g is grams and must be > 0" in body  # domain context injected


# -- honesty ------------------------------------------------------------------


def test_flagships_declare_no_label_rules():
    assert LEMAT_BULK.label_rules == ()
    assert METEORITES.label_rules == ()
