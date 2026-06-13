"""Trivial baselines the model must beat on held-out data (EVAL_PROTOCOL.md §6). Pure.

A reported model score is meaningless without a floor. Two floors:

* **vocabulary_floor** — the deterministic check the auditor already has: any value in the
  allowed vocabulary passes, so it judges *everything* plausible. It therefore scores 0 on
  the planted (implausible) cases. Beating it requires world knowledge, which is the whole
  point of the LLM-judged check.
* **majority_class** — predict the most common class of a *reference* split (dev), applied
  to the target split. With the deliberately balanced classes here it sits near 50%.
"""

from __future__ import annotations

from collections import Counter

from shared.metrics import Prediction


def vocabulary_floor(cases: list[dict], meta: dict) -> list[Prediction]:
    allowed = set(meta.get("allowed", ()))
    return [
        Prediction(c["id"], "plausible" if c["value"] in allowed else "implausible", c["expected"])
        for c in cases
    ]


def majority_class(cases: list[dict], reference_cases: list[dict]) -> list[Prediction]:
    counts = Counter(c["expected"] for c in reference_cases)
    # Deterministic tie-break (balanced classes tie): lowest label name wins.
    majority = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return [Prediction(c["id"], majority, c["expected"]) for c in cases]
