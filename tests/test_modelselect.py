"""Offline tests for per-domain model selection (``auditor.modelselect``).

No server is contacted: an ``httpx.MockTransport`` returns canned ``VerdictResult`` JSON,
so :func:`score_model` runs end to end (real prompt builder, real grading) without vLLM.
:func:`recommend` is pure and tested on synthetic scoreboards.
"""

import httpx

from auditor.datasets import get
from auditor.llm import LLMClient
from auditor.modelselect import (
    CaseResult,
    ScoreResult,
    case_to_issue,
    recommend,
    render_scoreboard,
    score_model,
)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def _verdict(v: str) -> str:
    return f'{{"verdict": "{v}", "confidence": 0.9, "reason": "r"}}'


def _client(chat, *, models_down: bool = False) -> LLMClient:
    """Client whose /models is OK (unless models_down) and whose /chat is `chat`
    (a callable handler, or a string used as the completion content)."""
    def handler(req):
        if req.url.path.endswith("/models"):
            if models_down:
                raise httpx.ConnectError("down", request=req)
            return httpx.Response(200, json={"data": []})
        return chat(req) if callable(chat) else _completion(chat)

    return LLMClient(model="m", transport=httpx.MockTransport(handler))


# Two cases with DISTINCTIVE messages so a handler can answer each one correctly.
CASES = [
    {"id": "a", "check": "units.out_of_range", "field": "nsites", "severity": "warn",
     "count": 1, "message": "ALPHA is impossible", "samples": ["nsites=0"], "expected": "real_defect"},
    {"id": "b", "check": "duplicates.duplicate_key", "field": "immutable_id", "severity": "error",
     "count": 122, "message": "BETA recurs by design", "samples": ["id=mp-149"], "expected": "expected_artifact"},
]


# -- case projection ----------------------------------------------------------


def test_case_to_issue_drops_label_keys():
    issue = case_to_issue(CASES[0])
    assert "expected" not in issue and "id" not in issue
    assert issue["check"] == "units.out_of_range" and issue["samples"] == ["nsites=0"]


# -- score_model (mocked transport) -------------------------------------------


def test_score_model_all_correct():
    spec = get("lemat_bulk")

    def chat(req):
        body = req.content.decode()
        verdict = "real_defect" if "ALPHA" in body else "expected_artifact"
        return _completion(_verdict(verdict))

    result = score_model(_client(chat), CASES, spec)
    assert (result.passed, result.total) == (2, 2)
    assert result.rate == 1.0
    assert all(r.ok for r in result.rows)


def test_score_model_counts_a_miss():
    spec = get("lemat_bulk")
    # Always answers real_defect: correct for case a, wrong for case b.
    result = score_model(_client(_verdict("real_defect")), CASES, spec)
    assert (result.passed, result.total) == (1, 2)
    by_id = {r.id: r for r in result.rows}
    assert by_id["a"].ok and not by_id["b"].ok


def test_score_model_records_call_failure_as_miss():
    spec = get("lemat_bulk")

    def chat(req):
        raise httpx.ConnectError("died", request=req)

    result = score_model(_client(chat), CASES, spec)
    assert result.passed == 0
    assert all(r.got == "ERROR" and not r.ok for r in result.rows)


# -- recommend (pure) ---------------------------------------------------------


def _score(model: str, passed: int, total: int) -> ScoreResult:
    rows = [
        CaseResult(f"c{i}", "real_defect",
                   "real_defect" if i < passed else "expected_artifact",
                   i < passed, "r")
        for i in range(total)
    ]
    return ScoreResult(model=model, rows=rows)


def test_recommend_clear_winner():
    rec = recommend([_score("A", 5, 5), _score("B", 3, 5)])
    assert rec.model == "A" and "A" in rec.reason


def test_recommend_reports_tie():
    rec = recommend([_score("A", 5, 5), _score("B", 5, 5)])
    assert rec.model in {"A", "B"}
    assert "tie" in rec.reason.lower() and "A" in rec.reason and "B" in rec.reason


def test_recommend_declines_on_thin_evidence():
    rec = recommend([_score("A", 2, 2), _score("B", 1, 2)], min_cases=3)
    assert rec.model is None and "need >= 3" in rec.reason


def test_recommend_handles_no_scores():
    assert recommend([ScoreResult(model="A", rows=[])]).model is None


# -- rendering ----------------------------------------------------------------


def test_render_scoreboard_orders_best_first_and_shows_recommendation():
    scores = [_score("worse", 1, 5), _score("better", 5, 5)]
    md = render_scoreboard("lemat_bulk", scores, recommend(scores))
    assert "lemat_bulk-verdict" in md
    assert md.index("better") < md.index("worse")  # best row first
    assert "**Recommended:** better" in md
