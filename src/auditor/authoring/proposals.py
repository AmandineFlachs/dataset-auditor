"""Propose structured rule candidates from column metadata.

The model's job is the one it is trusted with everywhere here: it *proposes* a check, it
never asserts a finding. :func:`propose` asks a local LLM for candidate rules from
aggregate metadata only (reusing ``research._metadata_text``, never raw rows); each is then
dry-run against the real check (see ``dryrun``) so a human/policy decides on real evidence.

The grammar is closed and small (see ``docs/design/guided-rule-authoring.md``): one flat
:class:`Candidate` carries a ``kind`` and only the fields that kind needs, which keeps the
LLM schema simple (a flat object the model fills by ``kind``) while mapping 1:1 onto the
real rule objects. ``label`` is deferred (its dry-run needs a live LLM that judges values).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from auditor.datasets import ConsistencyRule, DatasetSpec, FormulaRule, NearDupRule
from auditor.llm import LLMClient, LLMResponseError, LLMUnavailable
from auditor.research import _metadata_text

_PROPOSE_TIMEOUT = 180.0

Kind = Literal["range", "key", "consistency", "near_dup", "formula"]


class Candidate(BaseModel):
    """One structured, dry-runnable rule proposal. Only the fields for ``kind`` are used."""

    kind: Kind
    # Lenient so one sloppy candidate (a small model omitting a field) doesn't fail
    # validation for the WHOLE batch. A missing confidence defaults to a neutral 0.5,
    # which lands in the "ask" band rather than auto-accepting -- the safe direction.
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # range / key
    column: str | None = None
    # range
    min: float | None = None
    max: float | None = None
    exclusive_min: bool = False
    exclusive_max: bool = False
    # consistency
    group_by: str | None = None
    columns: list[str] = Field(default_factory=list)
    mode: Literal["exact", "numeric"] = "exact"
    tolerance: float = 0.0
    # near_dup
    content_key: str | None = None
    identity: str | None = None
    # formula
    reduced: str | None = None
    descriptive: str | None = None
    anonymous: str | None = None
    elements: str | None = None
    nelements: str | None = None

    # -- per-kind mapping ------------------------------------------------------

    def range_params(self) -> dict:
        """The ``range_rules[column]`` dict (range kind only); omits defaults."""
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

    def column_refs(self) -> list[str]:
        """Every data column this candidate references (used to validate it dry-runnable)."""
        if self.kind in ("range", "key"):
            return [self.column] if self.column else []
        if self.kind == "consistency":
            return ([self.group_by] if self.group_by else []) + list(self.columns)
        if self.kind == "near_dup":
            return [c for c in (self.content_key, self.identity) if c]
        if self.kind == "formula":
            return [c for c in (self.reduced, self.descriptive, self.anonymous,
                                self.elements, self.nelements) if c]
        return []

    def is_well_formed(self) -> bool:
        """True if the kind's required fields are present (a dry-runnable proposal)."""
        if self.kind == "range":
            return bool(self.column) and (self.min is not None or self.max is not None)
        if self.kind == "key":
            return bool(self.column)
        if self.kind == "consistency":
            return bool(self.group_by) and len(self.columns) >= 1
        if self.kind == "near_dup":
            return bool(self.content_key)
        if self.kind == "formula":
            anchor = self.reduced or self.descriptive
            return bool(anchor) and len(self.column_refs()) >= 2
        return False

    def to_rule(self):
        """Build the real rule object/value this candidate becomes (for dry-run + emit)."""
        if self.kind == "consistency":
            return ConsistencyRule(group_by=self.group_by, columns=tuple(self.columns),
                                   mode=self.mode, tolerance=self.tolerance)
        if self.kind == "near_dup":
            return NearDupRule(content_key=self.content_key, identity=self.identity)
        if self.kind == "formula":
            return FormulaRule(reduced=self.reduced, descriptive=self.descriptive,
                               anonymous=self.anonymous, elements=self.elements,
                               nelements=self.nelements)
        raise ValueError(f"to_rule() is for dataclass kinds, not {self.kind!r}")

    def describe(self) -> str:
        """One-line, human-facing description of the proposed check."""
        if self.kind == "range":
            return f"flag {self.column} {self._range_bound()}"
        if self.kind == "key":
            return f"require {self.column} to be unique"
        if self.kind == "consistency":
            return (f"within each {self.group_by}, require {', '.join(self.columns)} to agree "
                    f"({self.mode}{f', tol {self.tolerance}' if self.mode == 'numeric' else ''})")
        if self.kind == "near_dup":
            ident = f" under different {self.identity}" if self.identity else ""
            return f"flag rows sharing {self.content_key}{ident}"
        if self.kind == "formula":
            return f"require formula columns ({', '.join(self.column_refs())}) to encode one composition"
        return self.kind

    def _range_bound(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f"{'<=' if self.exclusive_min else '<'} {self.min}")
        if self.max is not None:
            parts.append(f"{'>=' if self.exclusive_max else '>'} {self.max}")
        return " or ".join(parts) if parts else "(no bound)"


class CandidateList(BaseModel):
    """Container so the LLM can return several candidates in one structured reply."""

    candidates: list[Candidate] = Field(default_factory=list)


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c != "row_id" and pd.api.types.is_numeric_dtype(df[c])]


def build_prompt(df: pd.DataFrame, spec: DatasetSpec) -> str:
    """The propose prompt: metadata + the closed grammar + a conservative instruction.

    Public so the (future) authoring benchmark can measure proposal quality on the exact
    prompt that ships, as the verdict/label benchmarks reuse their builders.
    """
    cols = [c for c in df.columns if c != "row_id"]
    numeric = _numeric_columns(df)
    grammar = (
        "Rule kinds you may propose (only where the data's structure supports it; do NOT "
        "force a kind that does not fit):\n"
        f"- range: a numeric column's plausible bounds. Fields: column (one of {numeric}), "
        "min/max, exclusive_min/exclusive_max. Use only where a value outside is physically "
        "or logically impossible (negative mass, future year, latitude past +/-90).\n"
        "- key: a column that must be a unique identifier. Field: column.\n"
        "- consistency: within rows sharing an id, some columns must agree. Fields: group_by "
        "(the id column), columns (the ones that must agree), mode ('exact' or 'numeric'), "
        "tolerance (numeric mode). Propose only when one column clearly identifies an entity "
        "whose other attributes are invariant.\n"
        "- near_dup: rows sharing a content/hash column under different identity ids are "
        "duplicate records. Fields: content_key, identity.\n"
        "- formula: chemical-formula columns that must encode one composition. Fields: "
        "reduced, descriptive, anonymous, elements, nelements (name those that exist).\n"
    )
    return (
        "You are helping a human author data-quality RULES for a dataset. From the column "
        "metadata and domain context below, propose a SMALL set of high-confidence rules. "
        "Prefer fewer, well-justified rules over many speculative ones; do not invent a "
        "bound or invariant you are unsure of (lower your confidence instead). Every rule is "
        "dry-run against the real data before anyone adopts it.\n\n"
        f"{grammar}\n"
        f"All columns: {', '.join(cols)}.\n"
        "For each rule give its kind, the fields that kind needs, a one-line rationale, and a "
        "confidence in [0,1].\n\n" + _metadata_text(df, spec)
    )


def propose(df: pd.DataFrame, spec: DatasetSpec, *, client: LLMClient | None = None) -> list[Candidate]:
    """Ask the local LLM for rule candidates, or return ``[]`` if offline.

    Degrades exactly like ``research.brief`` (no server -> no candidates). Drops any
    candidate that is malformed for its kind or references a column not in the data, so the
    rest of the session only ever sees dry-runnable proposals.
    """
    client = client or LLMClient.from_env(timeout=_PROPOSE_TIMEOUT)
    if not client.available():
        return []
    present = set(df.columns)
    numeric = set(_numeric_columns(df))
    try:
        reply = client.judge(build_prompt(df, spec), CandidateList, context=spec.domain_context)
    except (LLMUnavailable, LLMResponseError):
        # No server, or a reply that would not validate even as the lenient schema: either
        # way, offer no candidates rather than crash the session (graceful degradation).
        return []
    out: list[Candidate] = []
    for c in reply.candidates:
        if not c.is_well_formed():
            continue
        refs = c.column_refs()
        if not refs or any(r not in present for r in refs):
            continue
        if c.kind == "range" and c.column not in numeric:
            continue  # a range bound only makes sense on a numeric column
        out.append(c)
    return out
