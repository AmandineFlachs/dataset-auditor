"""Tests for the opt-in reasoning mode and JSON extraction. Offline (MockTransport)."""

import json

import httpx
from pydantic import BaseModel

from auditor.llm import (
    DEFAULT_REASONING_MAX_TOKENS,
    DEFAULT_REASONING_TIMEOUT,
    DEFAULT_TIMEOUT,
    LLMClient,
    _extract_json,
)


class Verdict(BaseModel):
    plausible: bool
    reason: str


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


# -- _extract_json ------------------------------------------------------------


def test_extract_plain_json():
    assert json.loads(_extract_json('{"plausible": true, "reason": "x"}'))["plausible"] is True


def test_extract_strips_code_fence():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_strips_think_block_and_takes_trailing_object():
    reply = '<think>Helium is a gas, so solid is wrong.</think>\n{"plausible": false, "reason": "He is a gas"}'
    obj = json.loads(_extract_json(reply))
    assert obj["plausible"] is False


def test_extract_picks_last_object_after_prose():
    reply = 'Here is my answer:\n{"plausible": false, "reason": "wrong phase"}'
    assert json.loads(_extract_json(reply))["plausible"] is False


def test_extract_returns_cleaned_text_when_no_json():
    assert _extract_json("no json here") == "no json here"


# -- reasoning request shape --------------------------------------------------


def _capture_client(reply: str, **kwargs):
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(req.content.decode())
        return _completion(reply)

    client = LLMClient(transport=httpx.MockTransport(handler), **kwargs)
    return client, captured


def test_reasoning_mode_omits_json_grammar_and_sets_token_budget():
    reply = '<think>reasoning...</think>{"plausible": false, "reason": "ok"}'
    client, captured = _capture_client(reply, reasoning=True)
    v = client.judge("is this plausible?", Verdict)
    assert v.plausible is False  # parsed correctly through the think block
    payload = captured["payload"]
    assert "response_format" not in payload          # no JSON-grammar constraint
    assert payload["max_tokens"] == DEFAULT_REASONING_MAX_TOKENS


def test_strict_mode_still_uses_json_object():
    client, captured = _capture_client('{"plausible": true, "reason": "ok"}')
    client.judge("?", Verdict)
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_reasoning_bumps_default_timeout_only_when_unset():
    explicit = LLMClient(reasoning=True, timeout=42.0)
    assert explicit._http.timeout.read == 42.0
    bumped = LLMClient(reasoning=True)
    assert bumped._http.timeout.read == DEFAULT_REASONING_TIMEOUT
    strict = LLMClient()
    assert strict._http.timeout.read == DEFAULT_TIMEOUT


def test_from_env_enables_reasoning(monkeypatch):
    monkeypatch.setenv("AUDITOR_LLM_REASONING", "1")
    assert LLMClient.from_env().reasoning is True
    monkeypatch.setenv("AUDITOR_LLM_REASONING", "off")
    assert LLMClient.from_env().reasoning is False
