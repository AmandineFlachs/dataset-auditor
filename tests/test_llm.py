"""Offline tests for the local-LLM client.

No server is ever contacted: every test injects an ``httpx.MockTransport`` whose
handler returns canned responses (or raises transport errors) so the client's
behaviour is exercised deterministically. This is the property that lets the LLM
layer be tested in CI without vLLM running.
"""

import httpx
import pytest
from pydantic import BaseModel

from auditor.llm import (
    LLMBudgetExceeded,
    LLMClient,
    LLMResponseError,
    LLMTimeout,
    LLMUnavailable,
)


class Verdict(BaseModel):
    """A tiny schema standing in for a real judge result."""

    plausible: bool
    reason: str


def _client(handler, **kwargs) -> LLMClient:
    """Build a client whose every request is served by ``handler`` (no sockets)."""
    return LLMClient(transport=httpx.MockTransport(handler), **kwargs)


def _completion(content: str) -> httpx.Response:
    """Shape a minimal OpenAI-compatible chat-completion response."""
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
    )


# -- available() --------------------------------------------------------------


def test_available_true_when_models_ok():
    client = _client(lambda req: httpx.Response(200, json={"data": []}))
    assert client.available() is True


def test_available_false_on_transport_error():
    def boom(req):
        raise httpx.ConnectError("connection refused", request=req)

    # A down server must read as "not available", never as an exception.
    assert _client(boom).available() is False


def test_available_false_on_non_ok_status():
    # A reachable-but-not-ready server (503 'loading model') must read as unavailable,
    # distinct from the transport-error path above.
    client = _client(lambda req: httpx.Response(503, text="loading model"))
    assert client.available() is False


def test_available_does_not_count_against_budget():
    client = _client(lambda req: httpx.Response(200, json={"data": []}))
    client.available()
    assert client.calls_made == 0


# -- judge() happy path -------------------------------------------------------


def test_judge_returns_validated_model():
    payload = '{"plausible": false, "reason": "mass is negative"}'
    client = _client(lambda req: _completion(payload))
    result = client.judge("Is this row plausible?", Verdict)
    assert isinstance(result, Verdict)
    assert result.plausible is False
    assert result.reason == "mass is negative"
    assert client.calls_made == 1


def test_judge_strips_markdown_fences():
    fenced = '```json\n{"plausible": true, "reason": "ok"}\n```'
    client = _client(lambda req: _completion(fenced))
    assert client.judge("?", Verdict).plausible is True


def test_judge_injects_domain_context_into_system_message():
    captured = {}

    def handler(req):
        captured["body"] = req.content.decode()
        return _completion('{"plausible": true, "reason": "ok"}')

    client = _client(handler)
    client.judge("question", Verdict, context="mass_g is grams and must be > 0")
    assert "mass_g is grams and must be > 0" in captured["body"]
    # The schema is advertised to the model too, so it knows the target shape.
    assert "plausible" in captured["body"]


def test_judge_targets_chat_completions_endpoint_preserving_v1():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return _completion('{"plausible": true, "reason": "ok"}')

    _client(handler).judge("?", Verdict)
    # base_url normalization must keep the /v1 prefix rather than letting the
    # leading path slash wipe it.
    assert seen["url"].endswith("/v1/chat/completions")


# -- judge() failure modes ----------------------------------------------------


def test_judge_raises_unavailable_on_transport_error():
    def boom(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(LLMUnavailable):
        _client(boom).judge("?", Verdict)


def test_judge_raises_unavailable_on_server_error_status():
    client = _client(lambda req: httpx.Response(503, text="loading model"))
    with pytest.raises(LLMUnavailable):
        client.judge("?", Verdict)


def test_judge_raises_timeout_on_read_timeout():
    # A slow generation that overruns the timeout must read as LLMTimeout, not as a
    # generic "down" - so a caller can tell "too slow" from "absent".
    def slow(req):
        raise httpx.ReadTimeout("timed out", request=req)

    with pytest.raises(LLMTimeout):
        _client(slow).judge("?", Verdict)


def test_timeout_is_an_unavailable_subclass():
    # Graceful-degradation handlers (except LLMUnavailable) must still catch a
    # timeout, so a slow server never crashes an audit.
    assert issubclass(LLMTimeout, LLMUnavailable)


def test_judge_raises_response_error_on_unvalidatable_reply():
    # Valid JSON, wrong shape for Verdict -> a loud error, not silent bad data.
    client = _client(lambda req: _completion('{"not": "a verdict"}'))
    with pytest.raises(LLMResponseError):
        client.judge("?", Verdict, retries=1)


def test_judge_retries_then_succeeds():
    replies = iter(
        [
            "totally not json",  # first attempt fails validation
            '{"plausible": true, "reason": "recovered"}',  # retry succeeds
        ]
    )
    client = _client(lambda req: _completion(next(replies)))
    assert client.judge("?", Verdict, retries=1).reason == "recovered"
    assert client.calls_made == 2  # it really did re-ask


# -- budget cap ---------------------------------------------------------------


def test_budget_cap_raises_after_max_calls():
    client = _client(
        lambda req: _completion('{"plausible": true, "reason": "ok"}'), max_calls=2
    )
    client.judge("?", Verdict)
    client.judge("?", Verdict)
    with pytest.raises(LLMBudgetExceeded):
        client.judge("?", Verdict)
