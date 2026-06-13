"""A thin client for a *local* LLM, served by vLLM over its OpenAI-compatible API.

This is the Phase-3 foundation: the consistency / PII / label checks that need a
model all talk to it through here, and through here only. The module has three
jobs, and deliberately nothing more.

1. **Speak the OpenAI `/v1` wire format** to a local vLLM server, using plain
   ``httpx`` (no heavyweight SDK). No data ever leaves the machine.

2. **Return validated objects, not raw text.** :meth:`LLMClient.judge` takes a
   prompt *and a pydantic model* and gives back an instance of that model, parsed
   and validated. A check therefore receives typed data it can trust, the same way
   it trusts a ``Finding``; it never string-parses an LLM reply itself. The model's
   reasoning lives behind the same kind of contract as everything else.

3. **Degrade gracefully.** A local server is a flaky dependency: it may be down,
   loading, or slow. That must never break an audit. So transport failures raise a
   single, specific :class:`LLMUnavailable`, which a check catches to emit *one*
   ``info`` finding ("LLM checks skipped: server offline") and move on. The
   deterministic checks are wholly unaffected. :meth:`available` lets a caller make
   that decision once, up front, instead of per row.

Domain grounding (``DatasetSpec.domain_context``) is injected as *context, not a
persona*: it gives the model facts to reason with (units, ranges, invariants), not
an identity to role-play. See the field docstring in ``auditor.datasets``.

Everything here is constructed so tests run fully offline: pass a custom httpx
``transport`` (e.g. ``httpx.MockTransport``) and no socket is ever opened.
"""

from __future__ import annotations

import json
import os
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

# Local vLLM defaults. Overridable per instance or via environment so the same
# code points at a different host/model without edits.
DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "local-model"
DEFAULT_TIMEOUT = 30.0
# Reasoning models (e.g. Qwen3) emit a long <think> step before answering, which is
# both slower and incompatible with JSON-grammar-constrained decoding. When reasoning is
# enabled we give the request much more time and a token budget for the thinking.
DEFAULT_REASONING_TIMEOUT = 300.0
DEFAULT_REASONING_MAX_TOKENS = 2048
# A per-run guard so a buggy check can't fire thousands of calls at the server.
# Checks are expected to *sample* rows; this is the backstop, not the budget.
DEFAULT_MAX_CALLS = 200

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for every error this module raises."""


class LLMUnavailable(LLMError):
    """The server could not be reached (down, loading, or refused the connection).

    This is the *expected* failure. Checks catch it and skip gracefully; the audit
    continues with its deterministic findings intact.
    """


class LLMTimeout(LLMUnavailable):
    """The server *was* reachable but a request exceeded the client timeout.

    A subclass of :class:`LLMUnavailable` so every graceful-degradation handler
    (``except LLMUnavailable``) still catches it and skips — a slow server should
    never crash an audit. But it is a *distinct* type so a caller that wants to be
    honest can tell "the model is too slow" apart from "there is no server", instead
    of reporting a reachable-but-sluggish server as absent.
    """


class LLMResponseError(LLMError):
    """The server replied, but the reply could not be parsed/validated as the
    requested schema (even after a retry). A genuine problem worth surfacing,
    distinct from the server simply being absent."""


class LLMBudgetExceeded(LLMError):
    """The per-run call cap was hit — a safety backstop against a runaway check."""


class LLMClient:
    """A minimal OpenAI-compatible chat client aimed at a local vLLM server.

    Construct one per audit run. Inject ``transport`` (an ``httpx`` transport) to
    test without a live server. ``max_calls`` caps how many completions one run may
    make, independent of any single check.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "EMPTY",  # vLLM ignores it; OpenAI-compat clients still send one
        timeout: float = DEFAULT_TIMEOUT,
        max_calls: int = DEFAULT_MAX_CALLS,
        reasoning: bool = False,
        max_tokens: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.max_calls = max_calls
        self.reasoning = reasoning
        self.max_tokens = max_tokens
        self._calls = 0
        # A reasoning model needs far longer to think; bump the default timeout when it
        # is on, but never override a timeout the caller set explicitly.
        if reasoning and timeout == DEFAULT_TIMEOUT:
            timeout = DEFAULT_REASONING_TIMEOUT
        # httpx merges a relative request path onto base_url only when base_url ends
        # with "/" and the path does NOT start with "/". Normalize once here so the
        # "/v1" prefix is preserved (a leading-slash path would wipe it).
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    # -- lifecycle ---------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def calls_made(self) -> int:
        """How many completions this client has issued (for logging/budget)."""
        return self._calls

    # -- the two things checks actually call --------------------------------------

    def available(self) -> bool:
        """Return whether the server answers, with no exception either way.

        A cheap ``GET /models``. Call once per run to decide whether to attempt the
        LLM checks at all, so a down server costs one fast failure rather than one
        per row. Never counts against ``max_calls``.
        """
        try:
            resp = self._http.get("models")
        except httpx.HTTPError:
            return False
        return resp.status_code == httpx.codes.OK

    def judge(
        self,
        prompt: str,
        schema: type[T],
        *,
        context: str = "",
        retries: int = 1,
    ) -> T:
        """Ask the model and return an instance of ``schema``, parsed and validated.

        ``context`` is the dataset's ``domain_context`` (factual grounding, injected
        as a system message). The model is instructed to answer with JSON matching
        ``schema``; the reply is validated by pydantic, so a malformed answer is a
        loud :class:`LLMResponseError`, not silently-wrong data flowing downstream.

        Raises :class:`LLMUnavailable` if the server can't be reached,
        :class:`LLMResponseError` if it replies but the reply won't validate after
        ``retries``, and :class:`LLMBudgetExceeded` past the per-run cap.
        """
        messages = _build_messages(prompt, schema, context)
        last_error: Exception | None = None
        # One initial attempt plus `retries` re-asks. Each re-ask re-sends the same
        # messages; vLLM sampling means a fresh draw, often enough to fix a stray
        # non-JSON reply without elaborate repair logic.
        for _ in range(retries + 1):
            content = self._chat(messages)
            try:
                return schema.model_validate_json(_extract_json(content))
            except ValidationError as exc:
                last_error = exc
        raise LLMResponseError(
            f"model reply did not match {schema.__name__} after {retries + 1} "
            f"attempt(s): {last_error}"
        )

    # -- internals ---------------------------------------------------------------

    def _chat(self, messages: list[dict[str, str]]) -> str:
        """POST one chat completion and return the assistant's text content."""
        if self._calls >= self.max_calls:
            raise LLMBudgetExceeded(
                f"per-run LLM call cap of {self.max_calls} reached; checks should "
                f"sample rather than scan every row"
            )
        self._calls += 1
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,  # auditing wants determinism, not creativity
        }
        if self.reasoning:
            # Let the model think first: do NOT constrain the output to a JSON grammar
            # (that suppresses the <think> step and makes a small reasoning model
            # confabulate a confident wrong answer). Give it a token budget to finish,
            # then _extract_json pulls the final object out of the reply. Slower, but
            # far more accurate for reasoning models.
            payload["max_tokens"] = self.max_tokens or DEFAULT_REASONING_MAX_TOKENS
        else:
            # Bias the server toward emitting a bare JSON object. vLLM honours this;
            # we still validate, so it is a hint, not a guarantee.
            payload["response_format"] = {"type": "json_object"}
            if self.max_tokens is not None:
                payload["max_tokens"] = self.max_tokens
        try:
            resp = self._http.post("chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            # Reachable but too slow: a generation that ran past the timeout. Kept
            # distinct from "absent" so callers can say so honestly; still an
            # LLMUnavailable subclass, so graceful-degradation handlers still skip.
            raise LLMTimeout(f"local LLM request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            # Transport failure or a non-2xx status (server down/loading/erroring)
            # all collapse to the one "treat it as absent" signal checks expect.
            raise LLMUnavailable(f"local LLM request failed: {exc}") from exc

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMResponseError(f"unexpected completion shape: {exc}") from exc

    @classmethod
    def from_env(cls, **overrides: object) -> "LLMClient":
        """Build a client from ``AUDITOR_LLM_*`` env vars, with kwargs winning.

        Lets deployment point the tool at a different host/model without code
        changes: ``AUDITOR_LLM_BASE_URL``, ``AUDITOR_LLM_MODEL``, ``AUDITOR_LLM_KEY``.
        """
        env: dict[str, object] = {}
        if base := os.getenv("AUDITOR_LLM_BASE_URL"):
            env["base_url"] = base
        if model := os.getenv("AUDITOR_LLM_MODEL"):
            env["model"] = model
        if key := os.getenv("AUDITOR_LLM_KEY"):
            env["api_key"] = key
        if os.getenv("AUDITOR_LLM_REASONING", "").strip().lower() in {"1", "true", "yes", "on"}:
            env["reasoning"] = True
        env.update(overrides)
        return cls(**env)  # type: ignore[arg-type]


def _build_messages(
    prompt: str, schema: type[BaseModel], context: str
) -> list[dict[str, str]]:
    """Assemble the system+user messages: grounding, schema, then the question."""
    schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    system = [
        "You are auditing a scientific dataset for data-quality problems.",
        "Reason only from the data and the factual context provided; do not invent "
        "domain facts.",
        f"Respond with a single JSON object and nothing else, matching this schema:\n{schema_json}",
    ]
    if context:
        # Grounding as context, not persona — facts to reason with.
        system.insert(1, f"Domain context (factual grounding):\n{context}")
    return [
        {"role": "system", "content": "\n\n".join(system)},
        {"role": "user", "content": prompt},
    ]


def _strip_code_fences(text: str) -> str:
    """Strip a ```...``` / ```json fence if the model wrapped its JSON in one.

    Small models do this often despite instructions; cheaper to tolerate than to
    fail validation over formatting.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    if s[:4].lower() == "json":
        s = s[4:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_think(text: str) -> str:
    """Drop a reasoning model's ``<think>...</think>`` block, keeping the answer after it.

    In reasoning mode the model thinks out loud before emitting JSON. If the server has a
    reasoning parser the think text is already separated; if not, it is inline here.
    """
    return _THINK_RE.sub("", text)


def _last_json_object(text: str) -> str | None:
    """Return the last substring of ``text`` that decodes as a complete JSON object.

    After thinking, the answer object sits at the end of the reply (possibly after prose).
    Trying ``raw_decode`` from each ``{`` and keeping the last full parse finds it without
    fragile regex brace-matching.
    """
    decoder = json.JSONDecoder()
    best: str | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                _, end = decoder.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            best = text[i : i + end]
    return best


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a reply: strip a think block and fences, then take the
    last complete object. Handles both the strict (already-JSON) and reasoning paths; if
    nothing parses, returns the cleaned text so validation raises a meaningful error."""
    s = _strip_code_fences(_strip_think(text)).strip()
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        obj = _last_json_object(s)
        return obj if obj is not None else s


if __name__ == "__main__":
    # Run me directly (`python src/auditor/llm.py`) to probe a local server. Needs
    # no model loaded to demonstrate graceful degradation — it just reports reach.
    client = LLMClient.from_env()
    if client.available():
        print(f"local LLM reachable at {client._http.base_url} (model={client.model})")
    else:
        print("local LLM not reachable - Phase-3 LLM checks would skip gracefully")
