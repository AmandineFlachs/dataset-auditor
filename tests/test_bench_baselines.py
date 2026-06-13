"""Baseline tests. Model-free."""

from shared import baselines, metrics

META = {"allowed": ["solid", "liquid", "gas"]}


def test_vocabulary_floor_calls_everything_plausible():
    cases = [
        {"id": "a", "value": "solid", "expected": "plausible"},
        {"id": "b", "value": "gas", "expected": "implausible"},   # planted defect
    ]
    preds = baselines.vocabulary_floor(cases, META)
    assert [p.predicted for p in preds] == ["plausible", "plausible"]
    # scores 0 on the planted (implausible) case -> the floor a model must beat
    impl_only = [p for p in preds if p.expected == "implausible"]
    assert metrics.accuracy(impl_only) == 0.0


def test_majority_class_uses_reference_distribution():
    target = [{"id": "t", "value": "solid", "expected": "implausible"}]
    reference = [
        {"id": "r1", "expected": "plausible"},
        {"id": "r2", "expected": "plausible"},
        {"id": "r3", "expected": "implausible"},
    ]
    preds = baselines.majority_class(target, reference)
    assert preds[0].predicted == "plausible"  # majority of the reference
