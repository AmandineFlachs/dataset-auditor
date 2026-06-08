"""Offline tests for the Phase-D research briefing (mocked LLM client)."""

import httpx
import pandas as pd
import pytest

from auditor import research
from auditor.datasets import METEORITES
from auditor.llm import LLMClient, LLMTimeout

_BRIEFING_JSON = (
    '{"summary":"Recovered meteorite landings.",'
    '"columns":[{"column":"mass_g","likely_meaning":"mass in grams","units":"g",'
    '"plausible_range":"> 0","pitfalls":"zeros are placeholders"}],'
    '"dataset_pitfalls":["(0,0) coordinates are a missing-location placeholder"],'
    '"suggested_checks":["mass_g must be > 0"]}'
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


def _df():
    return pd.DataFrame(
        {"row_id": [0, 1], "mass_g": [1.0, 2.0], "year": [1990, 2001], "fall": ["Fell", "Found"]}
    )


def test_brief_returns_structured_briefing():
    b = research.brief(_df(), METEORITES, client=_client_for(_BRIEFING_JSON))
    assert b is not None
    assert b.summary
    assert b.columns[0].column == "mass_g"
    assert "mass_g must be > 0" in b.suggested_checks


def test_brief_returns_none_when_offline():
    client = _client_for(_BRIEFING_JSON, models_exc=True)
    assert research.brief(_df(), METEORITES, client=client) is None


def test_brief_surfaces_timeout_rather_than_pretending_offline():
    # available() succeeds (server is there), but the generation times out. brief must
    # raise LLMTimeout, not return None - otherwise a slow server looks like no server.
    def chat(req):
        raise httpx.ReadTimeout("too slow", request=req)

    with pytest.raises(LLMTimeout):
        research.brief(_df(), METEORITES, client=_client_for(chat))


def test_prompt_uses_aggregate_metadata_not_raw_rows():
    captured = {}

    def chat(req):
        captured["body"] = req.content.decode()
        return _completion(_BRIEFING_JSON)

    research.brief(_df(), METEORITES, client=_client_for(chat))
    body = captured["body"]
    assert "mass_g" in body and "min=" in body  # numeric ranges (aggregate)
    assert "Fell" in body                        # categorical value-counts (aggregate)
    assert "advisory" in body.lower() or "not applied" in body.lower()  # advisory framing


def test_to_markdown_renders_sections():
    b = research.brief(_df(), METEORITES, client=_client_for(_BRIEFING_JSON))
    md = research.to_markdown(b, METEORITES)
    assert "# Research briefing: meteorites" in md
    assert "## Columns" in md and "`mass_g`" in md
    assert "Suggested checks" in md
    assert "advisory" in md.lower()  # the suggestions are explicitly not auto-applied
