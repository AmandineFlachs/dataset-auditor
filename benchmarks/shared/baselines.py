"""Trivial baselines every model must beat on held-out data (EVAL_PROTOCOL.md §6). Pure.

Task-agnostic (works for any label-plausibility task):

* **vocabulary_floor** — the deterministic check the auditor already has: any value in the
  allowed vocabulary passes, so it judges *everything* plausible and scores 0 on the
  planted (implausible) cases. Beating it requires world knowledge.
* **majority_class** — predict the most common class of a *reference* split (dev). With the
  deliberately balanced classes here it sits near 50%.
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
    majority = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return [Prediction(c["id"], majority, c["expected"]) for c in cases]
