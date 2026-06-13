"""Automated leakage linter — the [auto] half of docs/leakage_checklist.md. Pure.

It enforces the rule that destroyed the previous benchmark (EVAL_PROTOCOL.md §2): the
case *context* must never contain, name, or trivially reveal the answer, and the task
must carry no answer-bearing ``domain_context``. It scans the cases' context fields, NOT
the rendered prompt (the judged value and the allowed vocabulary legitimately appear in
the prompt; what must stay clean is the surrounding context).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeakageHit:
    case_id: str
    field: str
    reason: str


@dataclass(frozen=True)
class LeakageReport:
    hits: list[LeakageHit]

    @property
    def ok(self) -> bool:
        return not self.hits

    def summary(self) -> str:
        if self.ok:
            return "no leakage detected"
        return "\n".join(f"  {h.case_id} [{h.field}]: {h.reason}" for h in self.hits)


def _norm(value) -> str:
    return " ".join(str(value).lower().split())


def leakage_check(cases: list[dict], meta: dict) -> LeakageReport:
    """Scan cases for the leakage failure modes. Empty hit list == clean."""
    hits: list[LeakageHit] = []
    column = meta.get("column")
    allow = set(meta.get("context_fields", ()))
    policy = meta.get("leakage_policy", {})
    forbid = [t.lower() for t in policy.get("forbid_terms", ())]
    allowed_vocab = set(meta.get("allowed", ()))
    expected_values = set(meta.get("expected_values", ("plausible", "implausible")))

    # The task itself must not carry a domain_context (the exact prior leak vector).
    if meta.get("domain_context"):
        hits.append(LeakageHit("(meta)", "domain_context", "task defines a non-empty domain_context"))
    if policy.get("no_domain_context") and meta.get("domain_context"):
        hits.append(LeakageHit("(meta)", "domain_context", "leakage_policy forbids domain_context but one is set"))

    for i, c in enumerate(cases):
        cid = c.get("id", f"#{i}")
        value = _norm(c.get("value", ""))
        ctx = c.get("context", {}) or {}
        for key, raw in ctx.items():
            if allow and key not in allow:
                hits.append(LeakageHit(cid, key, f"context key {key!r} not in context_fields allow-list"))
            if key == column:
                hits.append(LeakageHit(cid, key, f"context reuses the judged column {column!r}"))
            nv = _norm(raw)
            if nv and (nv == value or value in nv.split()):
                hits.append(LeakageHit(cid, key, "context field contains the judged value"))
            for term in forbid:
                if term and term in nv:
                    hits.append(LeakageHit(cid, key, f"context field contains forbidden term {term!r}"))
        # Ground-truth sanity (cheap mislabel guard).
        if c.get("expected") not in expected_values:
            hits.append(LeakageHit(cid, "expected", f"expected {c.get('expected')!r} not a valid verdict"))
        if allowed_vocab and c.get("value") not in allowed_vocab:
            hits.append(LeakageHit(cid, "value", f"value {c.get('value')!r} not in allowed vocab"))

    return LeakageReport(hits)
