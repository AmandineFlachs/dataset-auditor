"""Scoring tests. Model-free."""

from shared import metrics
from shared.metrics import Prediction


def _preds(pairs):
    # pairs: list of (predicted, expected)
    return [Prediction(str(i), p, e) for i, (p, e) in enumerate(pairs)]


def test_confusion_and_accuracy():
    preds = _preds([
        ("implausible", "implausible"),  # tp
        ("implausible", "plausible"),    # fp
        ("plausible", "implausible"),    # fn
        ("plausible", "plausible"),      # tn
    ])
    assert metrics.confusion(preds) == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert metrics.accuracy(preds) == 0.5


def test_precision_recall_f1():
    preds = _preds([
        ("implausible", "implausible"),
        ("implausible", "implausible"),
        ("plausible", "implausible"),   # missed one positive
        ("plausible", "plausible"),
    ])
    prf = metrics.precision_recall_f1(preds)
    assert prf["precision"] == 1.0           # 2 tp, 0 fp
    assert round(prf["recall"], 3) == 0.667  # 2 tp, 1 fn
    assert 0.79 < prf["f1"] < 0.81


def test_weighted_accuracy_respects_class_weights():
    preds = _preds([("implausible", "implausible"), ("plausible", "implausible")])
    # both expected implausible; one correct -> 0.5 regardless of weight
    assert metrics.weighted_accuracy(preds, {"implausible": 3.0}) == 0.5


def test_wilson_interval_bounds():
    assert metrics.wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = metrics.wilson_interval(12, 24)
    assert lo < 0.5 < hi and 0.0 < lo and hi < 1.0
    assert round(lo, 2) == 0.31 and round(hi, 2) == 0.69


def test_score_split_shape():
    out = metrics.score_split(_preds([("implausible", "implausible"), ("plausible", "plausible")]))
    assert out["n"] == 2 and out["accuracy"] == 1.0
    for key in ("accuracy_ci95", "ci95_halfwidth", "confusion", "precision", "recall", "f1", "scorer_version"):
        assert key in out
    assert out["scorer_version"] == metrics.SCORER_VERSION
