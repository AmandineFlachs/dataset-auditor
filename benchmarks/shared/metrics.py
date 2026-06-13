"""Scoring for benchmark predictions. Pure: stdlib only.

The scorer is *versioned* (``SCORER_VERSION``): changing how grading works requires a
bump, which invalidates prior held-out numbers (EVAL_PROTOCOL.md §5). The positive class
is ``implausible`` — catching the planted defects is the job the label check exists for,
so precision/recall/F1 are reported for that class, not just accuracy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

POSITIVE = "implausible"
SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class Prediction:
    case_id: str
    predicted: str
    expected: str
    confidence: float | None = None

    @property
    def correct(self) -> bool:
        return self.predicted == self.expected


def confusion(preds: list[Prediction], positive: str = POSITIVE) -> dict:
    tp = fp = tn = fn = 0
    for p in preds:
        pred_pos, exp_pos = p.predicted == positive, p.expected == positive
        if pred_pos and exp_pos:
            tp += 1
        elif pred_pos and not exp_pos:
            fp += 1
        elif not pred_pos and exp_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def accuracy(preds: list[Prediction]) -> float:
    return sum(p.correct for p in preds) / len(preds) if preds else 0.0


def weighted_accuracy(preds: list[Prediction], weights: dict) -> float:
    """Accuracy with per-(expected-)class weights, e.g. to balance uneven classes."""
    num = sum(weights.get(p.expected, 1.0) * p.correct for p in preds)
    den = sum(weights.get(p.expected, 1.0) for p in preds)
    return num / den if den else 0.0


def precision_recall_f1(preds: list[Prediction], positive: str = POSITIVE) -> dict:
    c = confusion(preds, positive)
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion — sane at small n, where a
    naive Wald interval misbehaves. This is the interval EVAL_PROTOCOL.md §6 requires
    every held-out accuracy to carry."""
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def score_split(preds: list[Prediction], weights: dict | None = None) -> dict:
    """The full, serialisable score for one split's predictions."""
    n = len(preds)
    k = sum(p.correct for p in preds)
    lo, hi = wilson_interval(k, n)
    out = {
        "n": n,
        "correct": k,
        "accuracy": round(accuracy(preds), 4),
        "accuracy_ci95": [round(lo, 4), round(hi, 4)],
        "ci95_halfwidth": round((hi - lo) / 2, 4),
        "confusion": confusion(preds),
        "positive_class": POSITIVE,
        "scorer_version": SCORER_VERSION,
        **{k2: round(v, 4) for k2, v in precision_recall_f1(preds).items()},
    }
    if weights:
        out["weighted_accuracy"] = round(weighted_accuracy(preds, weights), 4)
    return out
