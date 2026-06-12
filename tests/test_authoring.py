"""Offline tests for guided rule-authoring (slice 1: range).

All model-free: ``dry_run`` runs the real check on a fixture DataFrame; ``propose`` is
exercised through an ``httpx.MockTransport`` (no vLLM); policy and session logic are pure.
"""

import httpx
import pandas as pd

from auditor.authoring import (
    Candidate,
    classify,
    dry_run,
    model_decide,
    propose,
    run_session,
)
from auditor.authoring.resolve import format_question
from auditor.authoring.session import emit_fragment
from auditor.datasets import METEORITES, get
from auditor.llm import LLMClient


def _df():
    # mass_g has two non-positive values (rows 1,3); year has one future value (row 2).
    return pd.DataFrame({
        "row_id": [0, 1, 2, 3],
        "mass_g": [10.0, 0.0, 5.0, -2.0],
        "year": [1990, 2000, 2999, 2010],
    })


# -- Candidate -> params mapping ----------------------------------------------


def test_candidate_params_maps_and_omits_defaults():
    c = Candidate(column="mass_g", min=0, exclusive_min=True, rationale="mass > 0", confidence=0.9)
    assert c.params() == {"min": 0, "exclusive_min": True}
    assert Candidate(column="x", rationale="r", confidence=0.5).params() == {}  # no bound


# -- dry_run against the real check -------------------------------------------


def test_dry_run_flags_real_rows_and_samples():
    cand = Candidate(column="mass_g", min=0, exclusive_min=True, rationale="mass > 0", confidence=0.9)
    ev = dry_run(cand, _df())
    assert ev.flag_count == 2 and ev.flag_rate == 0.5
    assert any("mass_g=" in s for s in ev.samples)


def test_dry_run_clean_rule_flags_nothing():
    cand = Candidate(column="year", max=3000, rationale="no future years", confidence=0.8)
    ev = dry_run(cand, _df())
    assert ev.flag_count == 0 and ev.flag_rate == 0.0 and ev.samples == []


# -- classify + model_decide policy -------------------------------------------


def _ev(flag_count, total):
    from auditor.authoring.dryrun import Evidence
    return Evidence(flag_count=flag_count, flag_rate=flag_count / total, samples=[])


def test_classify_bands():
    hi = Candidate(column="c", min=0, rationale="r", confidence=0.9)
    lo = Candidate(column="c", min=0, rationale="r", confidence=0.3)
    assert classify(hi, _ev(0, 1000)) == "auto-safe"        # ~0% + confident
    assert classify(hi, _ev(30, 1000)) == "ask"             # small plausible fraction
    assert classify(hi, _ev(600, 1000)) == "suspicious"     # ~most rows -> bound likely wrong
    assert classify(lo, _ev(0, 1000)) == "ask"              # tiny rate but low confidence


def test_model_decide_accepts_sound_skips_doubtful():
    hi = Candidate(column="c", min=0, exclusive_min=True, rationale="r", confidence=0.9)
    lo = Candidate(column="c", min=0, rationale="r", confidence=0.3)
    assert model_decide(hi, _ev(5, 1000)).action == "accept"       # confident + plausible
    assert model_decide(hi, _ev(900, 1000)).action == "skip"       # suspicious rate
    assert model_decide(lo, _ev(5, 1000)).action == "skip"         # low confidence
    # An accepted decision carries the params and a rationale, and is attributed to the model.
    res = model_decide(hi, _ev(5, 1000))
    assert res.final_params == {"min": 0, "exclusive_min": True} and res.decided_by == "model" and res.note


def test_format_question_mentions_impact():
    cand = Candidate(column="mass_g", min=0, exclusive_min=True, rationale="mass > 0", confidence=0.9)
    q = format_question(cand, dry_run(cand, _df()))
    assert "mass_g" in q and "flags 2 of 4 rows" in q


# -- propose via mocked transport ---------------------------------------------


def _client(reply_json: str) -> LLMClient:
    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": reply_json}}]})
    return LLMClient(transport=httpx.MockTransport(handler))


def test_propose_parses_candidates_and_drops_unknown_columns():
    reply = (
        '{"candidates": ['
        '{"kind":"range","column":"mass_g","min":0,"exclusive_min":true,"rationale":"mass>0","confidence":0.9},'
        '{"kind":"range","column":"not_a_column","min":0,"rationale":"x","confidence":0.5}'
        ']}'
    )
    cands = propose(_df(), METEORITES, client=_client(reply))
    assert [c.column for c in cands] == ["mass_g"]  # unknown/non-numeric column dropped
    assert cands[0].params() == {"min": 0, "exclusive_min": True}


def test_propose_offline_returns_empty():
    def handler(req):
        raise httpx.ConnectError("down", request=req)
    cands = propose(_df(), METEORITES, client=LLMClient(transport=httpx.MockTransport(handler)))
    assert cands == []


# -- session (hands-off, injected candidates -> no LLM) -----------------------


def test_run_session_hands_off_emits_fragment_and_log():
    cands = [
        Candidate(column="mass_g", min=0, exclusive_min=True, rationale="mass > 0", confidence=0.9),
        Candidate(column="year", min=0, max=2099, rationale="plausible CE years", confidence=0.85),
    ]
    # mass_g flags 2/4 = 50% -> suspicious -> skipped; year flags 1/4 = 25% -> accepted.
    result = run_session(_df(), get("meteorites"), "hands-off", candidates=cands)
    assert "year" in result.accepted and "mass_g" not in result.accepted
    assert len(result.log) == 2
    skipped = [e for e in result.log if e["action"] == "skip"][0]
    assert skipped["column"] == "mass_g" and skipped["decided_by"] == "model" and skipped["note"]
    # The emitted fragment is valid Python adopting exactly the accepted rule.
    ns: dict = {}
    exec(result.fragment, ns)
    assert ns["range_rules"] == {"year": {"min": 0, "max": 2099}}


def test_emit_fragment_empty_is_valid_python():
    ns: dict = {}
    exec(emit_fragment({}, "meteorites"), ns)
    assert ns["range_rules"] == {}
