"""A tiny local-model adapter so the Kaggle tasks can be validated OFFLINE.

`Task.evaluate(llm=[obj])` accepts any object exposing a ``.prompt(message, ...)`` method
(verified against kaggle-benchmarks 0.6.0). This wraps the same local vLLM server the
auditor uses (OpenAI-compatible ``/v1``), so Phase-2 validation reproduces the held-out
numbers without a Kaggle account or the Model Proxy.

It mirrors the auditor's *reasoning* path (``auditor.checks.labels`` runs in reasoning
mode): send the frozen prompt as a plain user turn with NO JSON-grammar constraint, let
the model think, strip the ``<think>`` block, and return the answer text. The Kaggle task's
``parse_verdict`` then reads plausible/implausible from that text — identical to how the
shipped check decides, minus the structured-output wrapper.

Config via the same env vars the auditor honours::

    AUDITOR_LLM_BASE_URL  (default http://localhost:8000/v1)
    AUDITOR_LLM_MODEL     (default local-model)
"""

from __future__ import annotations

import os
import re

import httpx

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "local-model"


class LocalVLLM:
    """Minimal OpenAI-compatible chat client returning the model's free-text answer."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300.0,
        max_tokens: int = 2048,
    ) -> None:
        base = (base_url or os.getenv("AUDITOR_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.model = model or os.getenv("AUDITOR_LLM_MODEL") or DEFAULT_MODEL
        self.name = self.model  # kaggle-benchmarks labels the leaderboard column by this
        self.max_tokens = max_tokens
        self._http = httpx.Client(
            base_url=base, timeout=timeout, headers={"Authorization": "Bearer EMPTY"}
        )

    def available(self) -> bool:
        try:
            return self._http.get("models").status_code == 200
        except httpx.HTTPError:
            return False

    def prompt(self, message: str, schema=str, reasoning=None, temperature: float = 0.0, **_) -> str:
        """Return the model's answer text (reasoning stripped). Signature is duck-compatible
        with ``kbench.llm.prompt`` so the same task code runs locally and on Kaggle."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
            "temperature": temperature,
            "max_tokens": self.max_tokens,  # budget for the <think> step; no JSON grammar
        }
        resp = self._http.post("chat/completions", json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _THINK_RE.sub("", content).strip()

    def close(self) -> None:
        self._http.close()
