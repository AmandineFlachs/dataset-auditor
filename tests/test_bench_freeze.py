"""Prompt-freeze + manifest tests. Model-free."""

import json

import pytest

from shared import cases, freeze


def test_prompt_identity_stable_and_template_sensitive():
    meta = cases.load_meta("labels_plausibility")
    assert freeze.prompt_identity(meta) == freeze.prompt_identity(meta)  # deterministic
    changed = {**meta, "context_fields": meta["context_fields"] + ["extra"]}
    assert freeze.prompt_identity(changed) != freeze.prompt_identity(meta)


def test_shipped_frozen_hash_matches_live_prompt():
    # The recorded freeze must match the current shipped prompt, or the held-out run is gated.
    freeze.verify_frozen_prompt("labels_plausibility")  # must not raise


def test_verify_raises_on_drift(monkeypatch):
    meta = cases.load_meta("labels_plausibility")
    tampered = {**meta, "frozen_prompt": {**meta["frozen_prompt"], "hash": "sha256:deadbeef"}}
    monkeypatch.setattr(freeze.cases_mod, "load_meta", lambda task: tampered)
    with pytest.raises(freeze.FrozenPromptDrift):
        freeze.verify_frozen_prompt("labels_plausibility")


def test_scorer_version_matches_meta():
    from shared import metrics
    meta = cases.load_meta("labels_plausibility")
    assert meta["scorer_version"] == metrics.SCORER_VERSION


def test_manifest_round_trips(tmp_path):
    m = freeze.RunManifest(
        task="labels_plausibility", split="dev", model="mock",
        frozen_prompt_hash="sha256:x", scorer_version="1.0.0", run_at="t",
        metrics={"accuracy": 0.5}, baselines={}, case_predictions=[],
    )
    p = freeze.write_manifest(m, tmp_path / "out.run.json")
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["task"] == "labels_plausibility" and loaded["metrics"]["accuracy"] == 0.5
