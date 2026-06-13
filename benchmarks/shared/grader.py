"""Turn a benchmark case into the SHIPPED label prompt and grade a verdict.

This reuses ``auditor.checks.labels.build_label_prompt`` and ``LabelVerdict`` verbatim
(EVAL_PROTOCOL.md §3.1), so the benchmark can never test a prompt the product doesn't
ship. Crucially there is **no** ``compose_prompt`` / ``domain_context`` step here: the
benchmark passes no answer-bearing grounding (§3.2). Pure: stdlib + pandas + auditor.
"""

from __future__ import annotations

import pandas as pd

from auditor.checks.labels import LabelVerdict, build_label_prompt
from auditor.datasets import LabelRule


def case_to_inputs(case: dict, meta: dict) -> tuple[LabelRule, pd.Series]:
    """Project a case onto the ``(LabelRule, row)`` that ``build_label_prompt`` consumes."""
    context = case.get("context", {}) or {}
    rule = LabelRule(
        column=meta["column"],
        context_columns=tuple(context.keys()),
        allowed=tuple(meta.get("allowed", ())),
    )
    row = pd.Series({meta["column"]: case["value"], **context})
    return rule, row


def case_to_prompt(case: dict, meta: dict) -> str:
    """The exact production prompt for this case — with no domain_context prepended."""
    rule, row = case_to_inputs(case, meta)
    return build_label_prompt(rule, row, list(rule.context_columns))


def verdict_to_label(verdict: LabelVerdict) -> str:
    """Map a parsed ``LabelVerdict`` to the case vocabulary."""
    return "plausible" if verdict.plausible else "implausible"


def grade_one(verdict: LabelVerdict, case: dict) -> bool:
    """True when the model's verdict matches the golden label."""
    return verdict_to_label(verdict) == case["expected"]
