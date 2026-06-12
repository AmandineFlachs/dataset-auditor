"""Offline tests for guided rule-authoring (all non-label kinds).

All model-free: ``dry_run`` runs the real checks on fixture DataFrames; ``propose`` is
exercised through an ``httpx.MockTransport`` (no vLLM); policy/session logic is pure.
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
from auditor.authoring.dryrun import Evidence
from auditor.authoring.resolve import format_question
from auditor.authoring.session import emit_fragment
from auditor.datasets import METEORITES, get
from auditor.llm import LLMClient


def _df():
    return pd.DataFrame({
        "row_id": [0, 1, 2, 3],
        "mass_g": [10.0, 0.0, 5.0, -2.0],   # range: <=0 flags rows 1,3
        "uid": ["a", "b", "b", "c"],        # key: 'b' repeats -> 2 flagged
        "grp": ["x", "x", "y", "y"],        # consistency group
        "attr": [1, 2, 3, 3],               # grp x disagrees (1 vs 2)
        "fp": ["h1", "h1", "h2", "h3"],     # near_dup content shared...
        "ident": ["i1", "i2", "i3", "i4"],  # ...under different ids
    })


def _cand(**kw):
    kw.setdefault("rationale", "r")
    kw.setdefault("confidence", 0.9)
    return Candidate(**kw)


# -- per-kind dry_run against the real checks ---------------------------------


def test_dry_run_range():
    ev = dry_run(_cand(kind="range", column="mass_g", min=0, exclusive_min=True), _df())
    assert ev.flag_count == 2 and ev.flag_rate == 0.5 and any("mass_g=" in s for s in ev.samples)


def test_dry_run_key_isolates_duplicate_key():
    ev = dry_run(_cand(kind="key", column="uid"), _df())
    assert ev.flag_count == 2  # only the duplicate-key signal, not exact-row dupes


def test_dry_run_consistency():
    ev = dry_run(_cand(kind="consistency", group_by="grp", columns=["attr"], mode="exact"), _df())
    assert ev.flag_count == 2


def test_dry_run_near_dup():
    ev = dry_run(_cand(kind="near_dup", content_key="fp", identity="ident"), _df())
    assert ev.flag_count == 2


def test_dry_run_formula():
    fdf = pd.DataFrame({"row_id": [0, 1], "reduced": ["CdInP", "Fe2O3"], "descriptive": ["Cd2In2P2", "FeO"]})
    ev = dry_run(_cand(kind="formula", reduced="reduced", descriptive="descriptive"), fdf)
    assert ev.flag_count == 1  # row 1 (FeO vs Fe2O3) mismatches; row 0 is a valid reduction


# -- mapping / well-formedness ------------------------------------------------


def test_range_params_omits_defaults():
    assert _cand(kind="range", column="m", min=0, exclusive_min=True).range_params() == {"min": 0, "exclusive_min": True}


def test_is_well_formed_per_kind():
    assert _cand(kind="range", column="m", min=0).is_well_formed()
    assert not _cand(kind="range", column="m").is_well_formed()         # no bound
    assert _cand(kind="key", column="uid").is_well_formed()
    assert not _cand(kind="consistency", group_by="g").is_well_formed()  # no columns
    assert _cand(kind="near_dup", content_key="fp").is_well_formed()
    assert not _cand(kind="formula", reduced="r").is_well_formed()       # needs >=2 columns


def test_describe_is_kind_specific():
    assert "unique" in _cand(kind="key", column="uid").describe()
    assert "agree" in _cand(kind="consistency", group_by="g", columns=["a"]).describe()
    assert "sharing" in _cand(kind="near_dup", content_key="fp").describe()


# -- classify + model_decide (kind-agnostic policy) ---------------------------


def _ev(flag_count, total):
    return Evidence(flag_count=flag_count, flag_rate=flag_count / total, samples=[])


def test_classify_bands():
    hi = _cand(kind="key", column="uid")               # confidence 0.9
    lo = _cand(kind="key", column="uid", confidence=0.3)
    assert classify(hi, _ev(0, 1000)) == "auto-safe"
    assert classify(hi, _ev(30, 1000)) == "ask"
    assert classify(hi, _ev(600, 1000)) == "suspicious"
    assert classify(lo, _ev(0, 1000)) == "ask"


def test_model_decide_accepts_sound_skips_doubtful():
    hi = _cand(kind="range", column="m", min=0, exclusive_min=True)
    lo = _cand(kind="range", column="m", min=0, confidence=0.3)
    assert model_decide(hi, _ev(5, 1000)).action == "accept"
    assert model_decide(hi, _ev(900, 1000)).action == "skip"      # suspicious rate
    assert model_decide(lo, _ev(5, 1000)).action == "skip"        # low confidence
    res = model_decide(hi, _ev(5, 1000))
    assert res.final is hi and res.decided_by == "model" and res.note


def test_format_question_mentions_impact():
    cand = _cand(kind="range", column="mass_g", min=0, exclusive_min=True)
    assert "flags 2 of 4 rows" in format_question(cand, dry_run(cand, _df()))


# -- ask_human edit path: re-dry-run before adopting --------------------------


def _patch_typer(monkeypatch, prompts, confirm):
    import typer
    answers = iter(prompts)
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: next(answers))
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: confirm)
    monkeypatch.setattr(typer, "echo", lambda *a, **k: None)


def test_edit_redryruns_and_adopts_on_confirm(monkeypatch):
    from auditor.authoring.resolve import ask_human
    cand = _cand(kind="range", column="mass_g", min=0, exclusive_min=True)  # original flags 2/4
    _patch_typer(monkeypatch, prompts=["e", "", "100"], confirm=True)       # edit to max=100
    res = ask_human(cand, dry_run(cand, _df()), _df())
    assert res.action == "edit" and res.final.max == 100
    assert "flags 0 rows" in res.note  # re-dry-run actually ran: 2 -> 0 under the new bound


def test_edit_rejected_after_redryrun_skips(monkeypatch):
    from auditor.authoring.resolve import ask_human
    cand = _cand(kind="range", column="mass_g", min=0, exclusive_min=True)
    _patch_typer(monkeypatch, prompts=["e", "0", "2025"], confirm=False)    # see impact, reject
    res = ask_human(cand, dry_run(cand, _df()), _df())
    assert res.action == "skip" and "rejected" in res.note


# -- propose via mocked transport ---------------------------------------------


def _client(reply_json: str) -> LLMClient:
    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": reply_json}}]})
    return LLMClient(transport=httpx.MockTransport(handler))


def test_propose_parses_kinds_and_drops_invalid():
    reply = (
        '{"candidates": ['
        '{"kind":"range","column":"mass_g","min":0,"exclusive_min":true,"rationale":"mass>0","confidence":0.9},'
        '{"kind":"key","column":"uid","rationale":"uid unique","confidence":0.8},'
        '{"kind":"range","column":"not_a_column","min":0,"rationale":"x","confidence":0.5},'
        '{"kind":"range","column":"mass_g","rationale":"no bound","confidence":0.4}'
        ']}'
    )
    cands = propose(_df(), METEORITES, client=_client(reply))
    kinds = [(c.kind, c.column) for c in cands]
    assert ("range", "mass_g") in kinds and ("key", "uid") in kinds
    assert ("range", "not_a_column") not in kinds  # unknown column dropped
    assert len([c for c in cands if c.kind == "range"]) == 1  # the no-bound range dropped


def test_propose_tolerates_candidate_missing_rationale():
    # A small model omitting a field for ONE candidate must not sink the whole batch.
    reply = (
        '{"candidates": ['
        '{"kind":"key","column":"uid","confidence":0.8},'   # no rationale
        '{"kind":"range","column":"mass_g","min":0,"rationale":"mass>0","confidence":0.9}'
        ']}'
    )
    cands = propose(_df(), METEORITES, client=_client(reply))
    assert {c.kind for c in cands} == {"key", "range"}
    assert next(c for c in cands if c.kind == "key").confidence == 0.8


def test_propose_offline_returns_empty():
    def handler(req):
        raise httpx.ConnectError("down", request=req)
    assert propose(_df(), METEORITES, client=LLMClient(transport=httpx.MockTransport(handler))) == []


# -- session + emit (multi-kind, hands-off, injected -> no LLM) ---------------


def test_run_session_hands_off_emits_multi_kind_fragment():
    cands = [
        _cand(kind="range", column="mass_g", min=0, exclusive_min=True),  # flags 2/4=50% -> suspicious -> skip
        _cand(kind="key", column="uid"),                                  # flags 2/4=50% -> suspicious -> skip
        _cand(kind="consistency", group_by="grp", columns=["attr"]),      # flags 2/4=50% -> suspicious -> skip
    ]
    result = run_session(_df(), get("meteorites"), "hands-off", candidates=cands)
    # All three flag 50% here, so the suspicious-rate guard skips them all (honest, not silent).
    assert result.accepted == []
    assert all(e["action"] == "skip" and e["decided_by"] == "model" for e in result.log)
    assert len(result.log) == 3


def test_emit_fragment_renders_valid_python_for_each_kind():
    accepted = [
        _cand(kind="range", column="mass_g", min=0, exclusive_min=True),
        _cand(kind="key", column="uid"),
        _cand(kind="consistency", group_by="grp", columns=["attr"], mode="exact"),
        _cand(kind="near_dup", content_key="fp", identity="ident"),
    ]
    frag = emit_fragment(accepted, "demo")
    ns: dict = {}
    exec(frag, ns)
    assert ns["range_rules"] == {"mass_g": {"min": 0.0, "exclusive_min": True}}
    assert ns["key_column"] == "uid"
    assert ns["consistency_rules"][0].group_by == "grp" and ns["consistency_rules"][0].columns == ("attr",)
    assert ns["near_dup_rules"][0].content_key == "fp"


def test_emit_fragment_empty():
    assert "no rules adopted" in emit_fragment([], "demo")
