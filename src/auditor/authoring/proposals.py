"""Propose structured range rules from column metadata (the first authoring slice).

The model's job here is the one it is trusted with everywhere in this project: it
*proposes* a check, it never asserts a finding. :func:`propose` asks a local LLM for
candidate range bounds from aggregate metadata only (reusing ``research._metadata_text``,
never raw rows), and returns them as validated :class:`Candidate` objects. Each is then
dry-run against the real check (see ``dryrun``) so the human/policy decides on real
evidence, not the model's say-so.

Slice 1 is ``range`` only (see ``docs/design/guided-rule-authoring.md``); other kinds are
the same loop with a different params->rule mapping.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from auditor.datasets import DatasetSpec
from auditor.llm import LLMClient, LLMUnavailable
from auditor.research import _metadata_text

_PROPOSE_TIMEOUT = 180.0


class Candidate(BaseModel):
    """One structured, dry-runnable range proposal (maps 1:1 onto a ``range_rules`` entry)."""

    kind: Literal["range"] = "range"
    column: str
    min: float | None = None
    max: float | None = None
    exclusive_min: bool = False
    exclusive_max: bool = False
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)

    def params(self) -> dict:
        """The ``range_rules[column]`` dict this candidate becomes (omitting defaults)."""
        p: dict = {}
        if self.min is not None:
            p["min"] = self.min
        if self.max is not None:
            p["max"] = self.max
        if self.exclusive_min:
            p["exclusive_min"] = True
        if self.exclusive_max:
            p["exclusive_max"] = True
        return p


class CandidateList(BaseModel):
    """Container so the LLM can return several candidates in one structured reply."""

    candidates: list[Candidate] = Field(default_factory=list)


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c != "row_id" and pd.api.types.is_numeric_dtype(df[c])]


def build_prompt(df: pd.DataFrame, spec: DatasetSpec) -> str:
    """The propose prompt: metadata + an explicit, conservative instruction.

    Public so the (future) authoring benchmark can measure proposal quality on the exact
    prompt that ships, the same way the verdict/label benchmarks reuse their builders.
    """
    numeric = _numeric_columns(df)
    return (
        "You are helping a human author data-quality RANGE rules for a dataset. From the "
        "column metadata and domain context below, propose plausible numeric bounds ONLY "
        "where a value outside them would be physically or logically impossible for the "
        "column's meaning (e.g. a negative mass, a future-dated year, a latitude past "
        "+/-90). Prefer a single open bound (just a min, or just a max) over inventing a "
        "tight two-sided range. Do NOT propose a bound you are unsure of; lower your "
        "confidence instead. Use exclusive_min/exclusive_max when the bound itself is "
        "invalid (e.g. mass must be > 0).\n\n"
        f"Propose range rules only for these numeric columns: {', '.join(numeric)}.\n"
        "For each, give the column, the bound(s), a one-line rationale, and a confidence "
        "in [0,1].\n\n" + _metadata_text(df, spec)
    )


def propose(df: pd.DataFrame, spec: DatasetSpec, *, client: LLMClient | None = None) -> list[Candidate]:
    """Ask the local LLM for range candidates, or return ``[]`` if offline.

    Degrades exactly like ``research.brief``: no server -> no candidates (the rest of the
    authoring session simply has nothing to offer, never crashes). Candidates naming a
    non-numeric or unknown column are dropped (the model proposed something undryrunnable).
    """
    client = client or LLMClient.from_env(timeout=_PROPOSE_TIMEOUT)
    if not client.available():
        return []
    numeric = set(_numeric_columns(df))
    try:
        reply = client.judge(build_prompt(df, spec), CandidateList, context=spec.domain_context)
    except LLMUnavailable:
        return []
    return [c for c in reply.candidates if c.column in numeric and c.params()]
